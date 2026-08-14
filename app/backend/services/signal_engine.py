"""Signal generation for Hyperliquid markets.

Provides a deterministic rule engine and an optional ``TradingAgentsGraph``
(LLM multi-agent) path. The LLM path is used only when a provider API key is
configured; otherwise the deterministic engine runs and the caller can include a
warning in the response.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.llm_cost import estimate_cost
from backend.services.llm_tracker import LlmUsageTracker
from backend.services.llm_usage_store import LlmUsageStore


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return df["close"].std() or 0.0
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _candle_features(client: HyperliquidClient, symbol: str) -> dict[str, Any]:
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = end - 7 * 24 * 60 * 60 * 1000
    df = client.get_candles_dataframe(symbol, interval="1h", start_ms=start, end_ms=end)
    if df.empty:
        return {"ok": False, "error": "no candle data"}

    close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2] if len(df) > 1 else close
    change_1h = (close - prev_close) / prev_close if prev_close else 0.0
    sma_20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else close
    sma_50 = float(df["close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else close
    atr = _atr(df, period=14)
    volume = float(df["volume"].iloc[-1] or 0)
    trend = "up" if close > sma_20 > sma_50 else "down" if close < sma_20 < sma_50 else "neutral"
    return {
        "ok": True,
        "close": close,
        "change1h": change_1h,
        "sma20": sma_20,
        "sma50": sma_50,
        "atr": atr,
        "volume": volume,
        "trend": trend,
    }


def _build_signal(
    symbol: str,
    strategy: dict[str, Any] | None = None,
    forced_action: str | None = None,
) -> dict[str, Any]:
    """Build a signal dict from Hyperliquid market data and optional strategy."""
    client = HyperliquidClient()
    market = client.get_market(symbol)
    if market is None:
        raise ValueError(f"Symbol {symbol} not found on Hyperliquid")

    price = market["price"]
    funding = market.get("funding", 0.0)
    oi = market.get("openInterest", 0.0)

    features = _candle_features(client, symbol)
    book = client.get_orderbook(symbol, levels=10)

    # Configurable thresholds from strategy or defaults
    raw_cfg = strategy or {}
    risk_cfg = raw_cfg.get("riskConfig") or {}
    cfg = {**raw_cfg, **risk_cfg}
    long_funding_threshold = cfg.get("longFundingThreshold", -0.0005)
    short_funding_threshold = cfg.get("shortFundingThreshold", 0.0005)
    leverage = min(int(cfg.get("leverage", 3)), market.get("maxLeverage", 3))
    allocation = float(cfg.get("allocation", 0.10))
    confidence_floor = int(cfg.get("confidenceFloor", 60))

    imbalance = book.get("imbalance", 0.5)
    book_signal = "bullish" if imbalance > 0.55 else "bearish" if imbalance < 0.45 else "neutral"

    score = 50
    reasons: list[str] = []

    if features["ok"]:
        trend = features["trend"]
        change1h = features["change1h"]
        if trend == "up" and change1h > 0:
            score += 15
            reasons.append(f"short-term trend is up (SMA20/50 aligned, +{change1h * 100:.2f}% 1h)")
        elif trend == "down" and change1h < 0:
            score -= 15
            reasons.append(f"short-term trend is down (SMA20/50 aligned, {change1h * 100:.2f}% 1h)")
        else:
            reasons.append(f"price action is mixed ({change1h * 100:.2f}% 1h)")

        if book_signal == "bullish":
            score += 10
            reasons.append(f"order-book bid imbalance {imbalance:.2f} shows buying pressure")
        elif book_signal == "bearish":
            score -= 10
            reasons.append(f"order-book ask imbalance {imbalance:.2f} shows selling pressure")
        else:
            reasons.append("order-book is balanced")
    else:
        reasons.append("candle data unavailable; using snapshot only")

    funding_extreme = False
    if funding < long_funding_threshold:
        score += 10
        reasons.append(
            f"funding is negative ({funding:.6f}), shorts pay longs — contrarian long bias"
        )
        funding_extreme = True
    elif funding > short_funding_threshold:
        score -= 10
        reasons.append(
            f"funding is highly positive ({funding:.6f}), longs pay shorts — contrarian short bias"
        )
        funding_extreme = True
    else:
        reasons.append(f"funding is neutral ({funding:.6f})")

    if oi > 0:
        reasons.append(f"open interest is {oi:,.0f}")

    action = "HOLD"
    if score >= confidence_floor and funding_extreme and book_signal in ("bullish", "neutral"):
        action = "BUY"
    elif (
        score <= (100 - confidence_floor)
        and funding_extreme
        and book_signal in ("bearish", "neutral")
    ):
        action = "SELL"

    if score < confidence_floor and score > (100 - confidence_floor):
        action = "HOLD"

    if forced_action in ("BUY", "SELL", "HOLD"):
        action = forced_action

    # Conservative position sizing: notional in USDC, fixed to a $10k reference wallet
    # so the frontend can scale to the real wallet later.
    reference_wallet = 10_000.0
    notional = reference_wallet * allocation if action in ("BUY", "SELL") else 0.0
    size_coin = round(notional / price, 8) if price and notional else 0.0
    size_usd = round(notional, 2)

    entry = price
    atr = features.get("atr", price * 0.015) if features["ok"] else price * 0.015
    stop_distance = max(atr, price * 0.015)

    if action == "BUY":
        stop = round(entry - stop_distance, 8)
        target = round(entry + stop_distance * 2, 8)
    elif action == "SELL":
        stop = round(entry + stop_distance, 8)
        target = round(entry - stop_distance * 2, 8)
    else:
        stop = 0.0
        target = 0.0

    confidence = max(0, min(100, score))
    reasoning = (
        f"Rule engine scored {confidence}/100. "
        + " ".join(reasons)
        + (
            f". Suggested {action} ${size_usd} notional ({size_coin} {symbol}) at ${entry} with {leverage}x leverage."
            if action in ("BUY", "SELL")
            else f". Conditions do not meet the trade threshold; suggested {action}."
        )
    )

    return {
        "id": f"sig-{uuid.uuid4().hex[:8]}",
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "size": size_usd,
        "entry": round(entry, 8),
        "stop": round(stop, 8),
        "target": round(target, 8),
        "leverage": leverage,
        "reasoning": reasoning,
        "agents": ["Market", "Funding", "OrderBook"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "meta": {
            "market": market,
            "orderbook": book,
            "candleFeatures": features,
            "funding": funding,
            "openInterest": oi,
        },
    }


def _llm_available() -> bool:
    """Check whether any upstream LLM API key is present."""
    return any(
        os.environ.get(k)
        for k in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "ZHIPU_API_KEY",
            "ZHIPU_CN_API_KEY",
        )
    )


def generate_signal(
    symbol: str,
    strategy: dict[str, Any] | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Return a signal dict compatible with the frontend ``Signal`` type.

    When ``use_llm`` is True and an LLM API key is configured, the upstream
    ``TradingAgentsGraph`` is used with ``asset_type="crypto"``; otherwise the
    deterministic rule engine is used. In both cases market data comes from
    the Hyperliquid client.
    """
    if use_llm and _llm_available():
        try:
            return _generate_signal_llm(symbol, strategy)
        except Exception as exc:  # noqa: BLE001
            # Fall back to deterministic engine if the graph fails.
            signal = _generate_signal_deterministic(symbol, strategy)
            signal["reasoning"] = (
                f"LLM path failed ({exc}); using rule engine. {signal['reasoning']}"
            )
            signal["agents"].append("LLM(fallback)")
            return signal
    return _generate_signal_deterministic(symbol, strategy)


def _generate_signal_deterministic(
    symbol: str,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic rule-engine signal (renamed from the original implementation)."""
    return _build_signal(symbol, strategy)


def _generate_signal_llm(
    symbol: str,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the TradingAgentsGraph and normalize its decision to a frontend signal."""
    from tradingagents.agents.utils.rating import parse_rating
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = DEFAULT_CONFIG.copy()
    # Use Hyperliquid-style crypto pipeline and today's date.
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tracker = LlmUsageTracker()
    ta = TradingAgentsGraph(debug=False, config=config, callbacks=[tracker])
    final_state, decision = ta.propagate(symbol.upper(), trade_date, asset_type="crypto")
    full_text = final_state.get("final_trade_decision", "") or str(decision)
    rating = parse_rating(full_text)
    action_map = {
        "Buy": "BUY",
        "Overweight": "BUY",
        "Hold": "HOLD",
        "Underweight": "SELL",
        "Sell": "SELL",
    }
    action = action_map.get(rating, "HOLD")

    # Use deterministic sizing for the LLM recommendation.
    signal = _build_signal(symbol, strategy, forced_action=action)
    signal["agents"] = ["LLM-Research", "LLM-Trader", "LLM-Risk"]
    signal["reasoning"] = f"LLM Portfolio Manager rating: {rating}. {signal['reasoning']}"
    signal["meta"]["llmDecision"] = full_text
    signal["meta"]["llmUsage"] = {
        "tokensIn": tracker.tokens_in,
        "tokensOut": tracker.tokens_out,
        "llmCalls": tracker.llm_calls,
        "spend": round(estimate_cost(tracker.tokens_in, tracker.tokens_out), 4),
    }
    LlmUsageStore().record(tracker.tokens_in, tracker.tokens_out, tracker.llm_calls)
    return signal
