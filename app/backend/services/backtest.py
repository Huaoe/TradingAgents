"""Historical backtest engine for TradingAgents strategies on Hyperliquid.

The engine fetches OHLCV candles from the Hyperliquid public ``Info`` API and
merges hourly funding history for perps.  It then runs a bar-by-bar simulation
using the strategy's template + risk config to generate long/short/flat
signals, applies maker/taker fees, slippage, and funding costs, and computes
standard performance statistics.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.template_signals import (
    prepare_candles_features,
)
from backend.services.template_signals import (
    signal_for_bar as _template_signal_for_bar,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str) -> datetime:
    """Parse ISO date/datetime, accepting date-only strings."""
    text = value.strip()
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _annualization_factor(interval: str) -> float:
    """Periods per year for a given bar interval."""
    mapping = {
        "1m": 365 * 24 * 60,
        "5m": 365 * 24 * 12,
        "15m": 365 * 24 * 4,
        "1h": 365 * 24,
        "4h": 365 * 6,
        "1d": 365,
    }
    return mapping.get(interval, 365 * 24)


def _sharpe_ratio(equity_values: list[float], interval: str) -> float:
    """Annualised Sharpe ratio from the equity curve.

    Formula:  sharpe = (mean(per-bar equity return) / std(per-bar equity return))
                       * sqrt(periods_per_year)

    The result is clamped to the range [-50, 50] and gracefully falls back to
    0.0 when the equity curve has fewer than two points, when all returns are
    identical, or when the standard deviation is effectively zero / NaN.
    """
    if len(equity_values) < 2:
        return 0.0

    returns = pd.Series(equity_values).pct_change().dropna()
    if len(returns) < 1:
        return 0.0

    mean_return = float(returns.mean())
    std_return = float(returns.std(ddof=1))
    if not std_return or std_return < 1e-12 or np.isnan(std_return):
        return 0.0

    periods = _annualization_factor(interval)
    sharpe = (mean_return / std_return) * np.sqrt(periods)
    if not np.isfinite(sharpe):
        return 0.0

    return float(max(-50.0, min(50.0, sharpe)))


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _prepare_candles(candles: list[dict[str, Any]]) -> pd.DataFrame:
    """Prepare OHLCV candles with shifted, no-look-ahead indicator columns."""
    return prepare_candles_features(candles)


def _merge_funding(
    df: pd.DataFrame,
    funding_history: list[dict[str, Any]],
) -> pd.DataFrame:
    df["fundingRate"] = 0.0
    df["fundingEvents"] = [[] for _ in range(len(df))]
    df["fundingMedian168"] = float("nan")
    df["fundingStd168"] = float("nan")
    if not funding_history:
        return df
    ff = pd.DataFrame(funding_history)
    if ff.empty or "time" not in ff.columns:
        return df
    ff["time"] = pd.to_datetime(ff["time"], unit="ms", utc=True)
    ff = ff.set_index("time").sort_index()
    if "fundingRate" not in ff.columns:
        return df
    ff = ff[["fundingRate"]].astype(float)
    events = ff["fundingRate"].copy()
    for timestamp, rate in events.items():
        bar_index = int(df.index.searchsorted(timestamp, side="right") - 1)
        if 0 <= bar_index < len(df):
            df.iloc[bar_index, df.columns.get_loc("fundingEvents")].append(float(rate))
    # Reindex to include all candle timestamps and forward-fill only. Leading
    # gaps stay empty and are treated as zero funding by the caller.
    combined_index = df.index.union(ff.index)
    ff = ff.reindex(combined_index).sort_index()
    ff["fundingRate"] = ff["fundingRate"].ffill()
    df["fundingRate"] = ff.reindex(df.index)["fundingRate"].fillna(0.0)
    # A 168-bar trailing distribution is approximately seven days on 1h data.
    rates = df["fundingRate"].astype(float)
    df["fundingMedian168"] = rates.rolling(168, min_periods=168).median().shift(1)
    df["fundingStd168"] = rates.rolling(168, min_periods=168).std(ddof=1).shift(1)
    return df


def _signal_for_bar(
    df: pd.DataFrame,
    idx: int,
    strategy: dict[str, Any],
) -> tuple[int, int]:
    """Return (signal, confidence) for the bar at ``idx``.

    Delegates to the shared template scoring logic so that the same rules
    drive both the backtest and live signal generator.
    """
    return _template_signal_for_bar(df, idx, strategy)


def _yfinance_candles(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str,
) -> list[dict[str, Any]]:
    """Fallback to yfinance for spot-like or missing Hyperliquid data."""
    import yfinance as yf

    ticker = symbol.split("-")[0].split("/")[0]
    yf_interval = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}.get(
        interval, "1h"
    )
    df = yf.download(
        f"{ticker}-USD",
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=yf_interval,
        progress=False,
        multi_level_access=False,
    )
    if df.empty:
        return []
    df = df.reset_index()
    time_col = "Date" if "Date" in df.columns else df.columns[0]
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    records = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row[time_col])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        records.append(
            {
                "time": int(ts.timestamp() * 1000),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]) if "volume" in row else 0.0,
                "symbol": symbol,
                "interval": interval,
            }
        )
    return records


def _load_strategy(strategy: dict[str, Any] | None) -> dict[str, Any]:
    return strategy or {}


def _compute_signals(df: pd.DataFrame, strategy: dict[str, Any]) -> pd.DataFrame:
    signals = pd.Series(index=df.index, dtype=int)
    confidences = pd.Series(index=df.index, dtype=int)
    for i in range(len(df)):
        sig, conf = _signal_for_bar(df, i, strategy)
        signals.iloc[i] = sig
        confidences.iloc[i] = conf
    return pd.DataFrame({"signal": signals, "confidence": confidences})


def run_backtest(
    symbol: str,
    interval: str,
    start_at: str,
    end_at: str,
    strategy: dict[str, Any] | None = None,
    initial_balance: float = 10_000.0,
    maker_fee: float = 0.00015,
    taker_fee: float = 0.00045,
    slippage_pct: float = 0.00005,
    order_type: str = "taker",
    fee_source: str = "generic_default",
    slippage_source: str = "default",
) -> dict[str, Any]:
    """Run a bar-by-bar backtest and return a dict compatible with ``BacktestResult``."""
    strategy = _load_strategy(strategy or {})
    start_dt = _parse_iso(start_at)
    end_dt = _parse_iso(end_at)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    client = HyperliquidClient()
    candles = client.get_candles(symbol, interval, start_ms, end_ms)
    if not candles:
        candles = _yfinance_candles(symbol, start_dt, end_dt, interval)

    if not candles:
        raise ValueError(f"No candle data for {symbol} in the selected range")

    df = _prepare_candles(candles)
    if df.empty:
        raise ValueError("Candle data is empty after preparation")

    try:
        funding = client.get_funding_history(symbol, start_ms=start_ms, end_ms=end_ms)
    except Exception:
        funding = []
    df = _merge_funding(df, funding)

    cfg = strategy.get("riskConfig") or {}
    leverage = max(1, int(_safe_float(cfg.get("leverage"), 3)))
    allocation = max(0.0, min(1.0, _safe_float(cfg.get("allocation"), 0.10)))
    min_hold_bars = max(0, int(_safe_float(cfg.get("minHoldBars"), 0)))
    cooldown_bars = max(0, int(_safe_float(cfg.get("cooldownBars"), 0)))
    exit_hysteresis = cfg.get("exitHysteresis")
    exit_hysteresis = (
        max(0.0, min(100.0, _safe_float(exit_hysteresis))) if exit_hysteresis is not None else None
    )
    stop_loss_pct = max(0.0, _safe_float(cfg.get("stopLossPct"), 0.0))
    take_profit_pct = max(0.0, _safe_float(cfg.get("takeProfitPct"), 0.0))
    trailing_stop_pct = max(0.0, _safe_float(cfg.get("trailingStopPct"), 0.0))
    order_type = order_type if order_type in {"maker", "taker"} else "taker"

    market = client.get_market(symbol) or {}
    max_leverage = int(market.get("maxLeverage") or 3)
    leverage = min(leverage, max_leverage)

    out = _compute_signals(df, strategy)
    df["signal"] = out["signal"]
    df["confidence"] = out["confidence"]

    confidence_floor_value = int(_safe_float(cfg.get("confidenceFloor"), 60))
    final_signal = int(df["signal"].iloc[-1]) if not df.empty else 0
    long_signals = int((df["signal"] == 1).sum())
    short_signals = int((df["signal"] == -1).sum())
    flat_signals = int((df["signal"] == 0).sum())

    # Simulation state
    cash = float(initial_balance)
    equity_curve: list[dict[str, Any]] = []
    drawdown_curve: list[dict[str, Any]] = []
    price_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    peak = cash
    position: int = 0  # -1, 0, 1
    entry_price = 0.0
    entry_time = None
    entry_confidence = 0
    entry_notional = 0.0
    position_size_coin = 0.0
    cumulative_funding = 0.0
    entry_bar_index = -1
    last_exit_bar_index = -(10**9)
    highest_price = 0.0
    lowest_price = 0.0

    fee_rate = maker_fee if order_type == "maker" else taker_fee + slippage_pct

    def mark_equity(current_price: float, current_time: pd.Timestamp) -> None:
        nonlocal peak
        unrealized = 0.0
        if position != 0 and entry_price:
            if position == 1:
                unrealized = float(position_size_coin * (current_price - entry_price))
            else:
                unrealized = float(position_size_coin * (entry_price - current_price))
        total = float(cash + unrealized)
        equity_curve.append({"time": current_time.isoformat(), "equity": round(total, 2)})
        if total > peak:
            peak = total
        dd = (peak - total) / peak if peak > 0 else 0.0
        drawdown_curve.append({"time": current_time.isoformat(), "drawdown": round(dd * 100, 2)})
        price_curve.append(
            {"time": current_time.isoformat(), "close": round(float(current_price), 8)}
        )

    def open_position(new_position: int, price: float, time: pd.Timestamp, confidence: int) -> None:
        nonlocal \
            cash, \
            position, \
            entry_price, \
            entry_time, \
            entry_confidence, \
            entry_notional, \
            position_size_coin, \
            cumulative_funding, \
            entry_bar_index, \
            highest_price, \
            lowest_price
        position = new_position
        entry_price = float(price)
        entry_time = time
        entry_confidence = int(confidence)
        entry_notional = float(cash * allocation * leverage)
        # Cap notional by available leverage headroom
        max_notional = cash * leverage
        if entry_notional > max_notional:
            entry_notional = float(max_notional)
        position_size_coin = float(entry_notional / entry_price) if entry_price else 0.0
        cost = float(entry_notional * fee_rate)
        cash = float(cash - cost)
        cumulative_funding = 0.0
        entry_bar_index = i
        highest_price = entry_price
        lowest_price = entry_price

    def close_position(price: float, time: pd.Timestamp, exit_reason: str = "signal") -> None:
        nonlocal \
            cash, \
            position, \
            entry_price, \
            entry_time, \
            entry_confidence, \
            entry_notional, \
            position_size_coin, \
            cumulative_funding, \
            last_exit_bar_index, \
            entry_bar_index, \
            highest_price, \
            lowest_price
        if position == 0 or not entry_price:
            return
        close_price = float(price)
        if position == 1:
            gross_pnl = float(position_size_coin * (close_price - entry_price))
        else:
            gross_pnl = float(position_size_coin * (entry_price - close_price))
        exit_notional = float(position_size_coin * close_price)
        entry_cost = float(entry_notional * fee_rate)
        exit_cost = float(exit_notional * fee_rate)
        net_pnl = float(gross_pnl - entry_cost - exit_cost - cumulative_funding)
        cash = float(cash + gross_pnl - exit_cost - cumulative_funding)
        side = "LONG" if position == 1 else "SHORT"
        return_pct = float((net_pnl / entry_notional * 100) if entry_notional else 0.0)
        trades.append(
            {
                "entryTime": entry_time.isoformat() if entry_time else None,
                "exitTime": time.isoformat(),
                "symbol": symbol,
                "side": side,
                "entryPrice": round(float(entry_price), 8),
                "exitPrice": round(close_price, 8),
                "sizeCoin": round(float(position_size_coin), 8),
                "notional": round(float(entry_notional), 2),
                "leverage": leverage,
                "grossPnl": round(gross_pnl, 2),
                "fees": round(float(entry_cost + exit_cost), 2),
                "fundingCost": round(float(cumulative_funding), 2),
                "netPnl": round(net_pnl, 2),
                "returnPct": round(return_pct, 2),
                "confidence": int(entry_confidence),
                "exitReason": exit_reason,
            }
        )
        last_exit_bar_index = i
        position = 0
        entry_price = 0.0
        entry_time = None
        entry_confidence = 0
        entry_notional = 0.0
        position_size_coin = 0.0
        cumulative_funding = 0.0
        entry_bar_index = -1
        highest_price = 0.0
        lowest_price = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        price = row["close"]
        time = df.index[i]
        signal = int(row["signal"])

        # Funding cost for holding the position through this bar.
        if position != 0 and entry_notional:
            funding_cost = 0.0
            for hourly_rate in row.get("fundingEvents", []):
                rate = max(-0.04, min(0.04, _safe_float(hourly_rate)))
                funding_cost += position * position_size_coin * price * rate
            cash = float(cash - funding_cost)
            cumulative_funding = float(cumulative_funding + funding_cost)

        protective_exit = None
        protective_price = None
        if position != 0 and i > entry_bar_index:
            high = float(row["high"])
            low = float(row["low"])
            if position == 1:
                stop_price = entry_price * (1 - stop_loss_pct) if stop_loss_pct else None
                target_price = entry_price * (1 + take_profit_pct) if take_profit_pct else None
                trailing_price = (
                    highest_price * (1 - trailing_stop_pct) if trailing_stop_pct else None
                )
                stop_candidates = [
                    ("stop_loss", stop_price),
                    ("trailing_stop", trailing_price),
                ]
                stop_candidates = [
                    (reason, candidate)
                    for reason, candidate in stop_candidates
                    if candidate is not None
                ]
                stop_candidates.sort(key=lambda item: item[1], reverse=True)
                for reason, candidate in stop_candidates:
                    if low <= candidate:
                        protective_exit = reason
                        protective_price = candidate
                        break
                if protective_exit is None and target_price is not None and high >= target_price:
                    protective_exit = "take_profit"
                    protective_price = target_price
                if protective_exit is None:
                    highest_price = max(highest_price, high)
            else:
                stop_price = entry_price * (1 + stop_loss_pct) if stop_loss_pct else None
                target_price = entry_price * (1 - take_profit_pct) if take_profit_pct else None
                trailing_price = (
                    lowest_price * (1 + trailing_stop_pct) if trailing_stop_pct else None
                )
                stop_candidates = [
                    ("stop_loss", stop_price),
                    ("trailing_stop", trailing_price),
                ]
                stop_candidates = [
                    (reason, candidate)
                    for reason, candidate in stop_candidates
                    if candidate is not None
                ]
                stop_candidates.sort(key=lambda item: item[1])
                for reason, candidate in stop_candidates:
                    if high >= candidate:
                        protective_exit = reason
                        protective_price = candidate
                        break
                if protective_exit is None and target_price is not None and low <= target_price:
                    protective_exit = "take_profit"
                    protective_price = target_price
                if protective_exit is None:
                    lowest_price = min(lowest_price, low)

        if protective_exit is not None:
            close_position(float(protective_price), time, protective_exit)
        elif position != 0 and signal != position:
            can_signal_exit = i - entry_bar_index >= min_hold_bars
            if signal == 0 and exit_hysteresis is not None:
                if position == 1:
                    can_signal_exit = can_signal_exit and float(row["confidence"]) < exit_hysteresis
                else:
                    can_signal_exit = (
                        can_signal_exit and float(row["confidence"]) > 100 - exit_hysteresis
                    )
            if can_signal_exit:
                close_position(price, time, "signal")

        if (
            position == 0
            and signal != 0
            and (cooldown_bars == 0 or i - last_exit_bar_index > cooldown_bars)
        ):
            open_position(signal, price, time, int(row["confidence"]))

        mark_equity(price, time)

    # Close any open position at the final close.
    if position != 0:
        close_position(df["close"].iloc[-1], df.index[-1], "end_of_backtest")

    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else float(cash)
    total_return = float(
        (final_equity - initial_balance) / initial_balance * 100 if initial_balance else 0.0
    )
    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    benchmark_return = float((last_close / first_close - 1) * 100 if first_close else 0.0)

    equity_values = [float(pt["equity"]) for pt in equity_curve]
    sharpe = _sharpe_ratio(equity_values, interval)

    max_dd = float(max([pt["drawdown"] for pt in drawdown_curve]) if drawdown_curve else 0.0)

    wins = [t for t in trades if t["netPnl"] > 0]
    losses = [t for t in trades if t["netPnl"] <= 0]
    win_rate = float((len(wins) / len(trades) * 100) if trades else 0.0)
    net_profit = float(sum(t["netPnl"] for t in wins))
    net_loss = float(abs(sum(t["netPnl"] for t in losses)))
    profit_factor = float(
        net_profit / net_loss if net_loss > 0 else (math.inf if net_profit > 0 else 0.0)
    )
    gross_wins = [t for t in trades if t["grossPnl"] > 0]
    gross_losses = [t for t in trades if t["grossPnl"] <= 0]
    gross_profit = float(sum(t["grossPnl"] for t in gross_wins))
    gross_loss = float(abs(sum(t["grossPnl"] for t in gross_losses)))
    gross_profit_factor = float(
        gross_profit / gross_loss
        if gross_loss > 0
        else (math.inf if gross_profit > 0 else 0.0)
    )
    avg_trade_return = float(sum(t["returnPct"] for t in trades) / len(trades) if trades else 0.0)
    avg_win = float(sum(t["returnPct"] for t in wins) / len(wins) if wins else 0.0)
    avg_loss = float(sum(t["returnPct"] for t in losses) / len(losses) if losses else 0.0)

    # Monthly returns heatmap
    monthly: dict[str, float] = defaultdict(float)
    for pt in equity_curve:
        ts = pd.to_datetime(pt["time"])
        key = f"{ts.year}-{ts.month:02d}"
        monthly[key] = pt["equity"]
    monthly_returns: dict[str, float] = {}
    sorted_months = sorted(monthly.keys())
    for i, key in enumerate(sorted_months):
        if i == 0:
            monthly_returns[key] = 0.0
            continue
        prev = monthly[sorted_months[i - 1]]
        curr = monthly[key]
        if prev:
            monthly_returns[key] = round((curr / prev - 1) * 100, 2)
        else:
            monthly_returns[key] = 0.0

    def _fmt(value: float, decimals: int = 2) -> float:
        return float(round(float(value), decimals))

    avg_trade_confidence = float(
        sum(t["confidence"] for t in trades) / len(trades) if trades else 0.0
    )
    non_flat_signals = df.loc[df["signal"] != 0, "confidence"]
    avg_signal_confidence = float(non_flat_signals.mean()) if not non_flat_signals.empty else 0.0

    summary = {
        "initialBalance": _fmt(initial_balance),
        "finalBalance": _fmt(final_equity),
        "totalReturnPct": _fmt(total_return),
        "benchmarkReturnPct": _fmt(benchmark_return),
        "sharpeRatio": _fmt(sharpe),
        "maxDrawdownPct": _fmt(max_dd),
        "winRatePct": _fmt(win_rate),
        "profitFactor": _fmt(profit_factor) if not math.isinf(float(profit_factor)) else 999.99,
        "grossProfitFactor": (
            _fmt(gross_profit_factor) if not math.isinf(float(gross_profit_factor)) else 999.99
        ),
        "totalTrades": int(len(trades)),
        "avgTradeReturnPct": _fmt(avg_trade_return),
        "avgWinPct": _fmt(avg_win),
        "avgLossPct": _fmt(avg_loss),
        "avgConfidence": _fmt(avg_trade_confidence),
        "avgSignalConfidence": _fmt(avg_signal_confidence),
        "confidenceFloor": confidence_floor_value,
        "leverage": leverage,
        "allocation": _fmt(allocation),
        "finalSignal": final_signal,
        "longSignals": long_signals,
        "shortSignals": short_signals,
        "flatSignals": flat_signals,
        "startTime": df.index[0].isoformat(),
        "endTime": df.index[-1].isoformat(),
        "interval": interval,
        "symbol": symbol,
        "strategyName": strategy.get("name", ""),
        "makerFee": _fmt(maker_fee, 6),
        "takerFee": _fmt(taker_fee, 6),
        "slippagePct": _fmt(slippage_pct, 6),
        "orderType": order_type,
        "feeSource": fee_source,
        "slippageSource": slippage_source,
        "makerAssumption": "assumes fills; no queue modelling",
        "totalGrossPnl": _fmt(sum(t["grossPnl"] for t in trades)),
        "totalFees": _fmt(sum(t["fees"] for t in trades)),
        "totalFundingCost": _fmt(sum(t["fundingCost"] for t in trades)),
        "totalNetPnl": _fmt(sum(t["netPnl"] for t in trades)),
    }

    return {
        "summary": summary,
        "equity": equity_curve,
        "drawdown": drawdown_curve,
        "price": price_curve,
        "trades": trades,
        "monthlyReturns": monthly_returns,
    }
