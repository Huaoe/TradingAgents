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
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.set_index("time").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df["return"] = df["close"].pct_change()
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    df["std20"] = df["close"].rolling(20).std()
    df["upperBB"] = df["sma20"] + 2 * df["std20"]
    df["lowerBB"] = df["sma20"] - 2 * df["std20"]
    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)
    # Donchian channel (prior N bars, excluding the current bar) — used by the
    # Turtle Breakout and Grid Trading templates.
    df["donchianHigh"] = df["high"].rolling(20).max().shift(1)
    df["donchianLow"] = df["low"].rolling(20).min().shift(1)
    # Dual Thrust range inputs (prior N bars, excluding the current bar).
    dt_lookback = 4
    df["dtHH"] = df["high"].rolling(dt_lookback).max().shift(1)
    df["dtHC"] = df["close"].rolling(dt_lookback).max().shift(1)
    df["dtLC"] = df["close"].rolling(dt_lookback).min().shift(1)
    df["dtLL"] = df["low"].rolling(dt_lookback).min().shift(1)
    return df


def _merge_funding(
    df: pd.DataFrame,
    funding_history: list[dict[str, Any]],
) -> pd.DataFrame:
    df["fundingRate"] = 0.0
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
    # Reindex to include all candle timestamps, forward-fill, then back-fill.
    combined_index = df.index.union(ff.index)
    ff = ff.reindex(combined_index).sort_index()
    ff["fundingRate"] = ff["fundingRate"].ffill().bfill()
    df["fundingRate"] = ff.reindex(df.index)["fundingRate"].fillna(0.0)
    return df


def _signal_for_bar(
    df: pd.DataFrame,
    idx: int,
    strategy: dict[str, Any],
) -> int:
    """Return -1, 0, or 1 for the bar at ``idx``."""
    row = df.iloc[idx]
    if idx == 0 or pd.isna(row["sma50"]):
        return 0

    close = row["close"]
    prev_close = df["close"].iloc[idx - 1]
    sma20 = row["sma20"]
    sma50 = row["sma50"]
    rsi = row["rsi14"]
    upper = row["upperBB"]
    lower = row["lowerBB"]
    funding = row.get("fundingRate", 0.0)

    cfg = strategy.get("riskConfig") or {}
    long_thr = _safe_float(cfg.get("longFundingThreshold"), -0.0005)
    short_thr = _safe_float(cfg.get("shortFundingThreshold"), 0.0005)
    confidence_floor = int(_safe_float(cfg.get("confidenceFloor"), 60))
    template = strategy.get("template", "custom").replace("_", "-")

    trend_up = close > sma20 and sma20 > sma50 and close > prev_close
    trend_down = close < sma20 and sma20 < sma50 and close < prev_close

    def bound_score() -> int:
        if pd.notna(lower) and close < lower:
            return 10
        if pd.notna(upper) and close > upper:
            return -10
        return 0

    def rsi_score() -> int:
        if pd.isna(rsi):
            return 0
        if rsi < 30:
            return 10
        if rsi > 70:
            return -10
        return 0

    def funding_score() -> int:
        if funding < long_thr:
            return 15
        if funding > short_thr:
            return -15
        return 0

    score = 50
    if template == "momentum-breakout":
        if trend_up:
            score = 70
        elif trend_down:
            score = 30
        else:
            return 0
        score += funding_score()
    elif template == "mean-reversion":
        if rsi_score() > 0 and bound_score() > 0:
            score = 80
        elif rsi_score() < 0 and bound_score() < 0:
            score = 20
        else:
            return 0
        score += funding_score()
    elif template in ("funding-rate-arb", "hype-delta-neutral", "basis-arbitrage"):
        if funding < long_thr:
            score = 80
        elif funding > short_thr:
            score = 20
        else:
            return 0
    elif template == "trend-following":
        if trend_up:
            score = 70
        elif trend_down:
            score = 30
        else:
            return 0
        score += funding_score()
    elif template == "scalp-momentum":
        if pd.notna(upper) and close > upper and trend_up:
            score = 80
        elif pd.notna(lower) and close < lower and trend_down:
            score = 20
        else:
            return 0
        score += funding_score()
    elif template == "news-event":
        bar_range = row["high"] - row["low"]
        atr = row["atr14"]
        open_price = row["open"]
        if pd.notna(atr) and atr > 0 and bar_range > 1.5 * atr:
            if close > open_price and close > prev_close:
                score = 80
            elif close < open_price and close < prev_close:
                score = 20
            else:
                return 0
            score += funding_score()
        else:
            return 0
    elif template == "grid-trading":
        donchian_high = row.get("donchianHigh")
        donchian_low = row.get("donchianLow")
        if pd.isna(donchian_high) or pd.isna(donchian_low) or donchian_high == donchian_low:
            return 0
        range_span = donchian_high - donchian_low
        position_in_range = (close - donchian_low) / range_span
        if position_in_range <= 0.2:
            score = 70
        elif position_in_range >= 0.8:
            score = 30
        else:
            return 0
        score += funding_score()
    elif template == "dual-thrust":
        hh, hc, lc, ll = row.get("dtHH"), row.get("dtHC"), row.get("dtLC"), row.get("dtLL")
        if pd.isna(hh) or pd.isna(hc) or pd.isna(lc) or pd.isna(ll):
            return 0
        thrust_range = max(hh - lc, hc - ll)
        k1 = k2 = 0.5
        open_price = row["open"]
        upper_band = open_price + k1 * thrust_range
        lower_band = open_price - k2 * thrust_range
        if close > upper_band:
            score = 75
        elif close < lower_band:
            score = 25
        else:
            return 0
        score += funding_score()
    elif template == "turtle-breakout":
        donchian_high = row.get("donchianHigh")
        donchian_low = row.get("donchianLow")
        if pd.isna(donchian_high) or pd.isna(donchian_low):
            return 0
        if close > donchian_high:
            score = 75
        elif close < donchian_low:
            score = 25
        else:
            return 0
        score += funding_score()
    else:  # custom / fallback
        if trend_up:
            score += 15
        if trend_down:
            score -= 15
        score += rsi_score() + bound_score() + funding_score()

    if score >= confidence_floor:
        return 1
    if score <= (100 - confidence_floor):
        return -1
    return 0


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


def _compute_signals(df: pd.DataFrame, strategy: dict[str, Any]) -> pd.Series:
    signals = pd.Series(index=df.index, dtype=int)
    for i in range(len(df)):
        signals.iloc[i] = _signal_for_bar(df, i, strategy)
    return signals


def run_backtest(
    symbol: str,
    interval: str,
    start_at: str,
    end_at: str,
    strategy: dict[str, Any] | None = None,
    initial_balance: float = 10_000.0,
    maker_fee: float = 0.0002,
    taker_fee: float = 0.00045,
    slippage_pct: float = 0.0005,
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

    market = client.get_market(symbol) or {}
    max_leverage = int(market.get("maxLeverage") or 3)
    leverage = min(leverage, max_leverage)

    signals = _compute_signals(df, strategy)
    df["signal"] = signals

    # Simulation state
    cash = float(initial_balance)
    equity_curve: list[dict[str, Any]] = []
    drawdown_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    peak = cash
    position: int = 0  # -1, 0, 1
    entry_price = 0.0
    entry_time = None
    entry_notional = 0.0
    position_size_coin = 0.0
    cumulative_funding = 0.0

    fee_rate = taker_fee + slippage_pct

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

    def open_position(new_position: int, price: float, time: pd.Timestamp) -> None:
        nonlocal \
            cash, \
            position, \
            entry_price, \
            entry_time, \
            entry_notional, \
            position_size_coin, \
            cumulative_funding
        position = new_position
        entry_price = float(price)
        entry_time = time
        entry_notional = float(cash * allocation * leverage)
        # Cap notional by available leverage headroom
        max_notional = cash * leverage
        if entry_notional > max_notional:
            entry_notional = float(max_notional)
        position_size_coin = float(entry_notional / entry_price) if entry_price else 0.0
        cost = float(entry_notional * fee_rate)
        cash = float(cash - cost)
        cumulative_funding = 0.0

    def close_position(price: float, time: pd.Timestamp) -> None:
        nonlocal \
            cash, \
            position, \
            entry_price, \
            entry_time, \
            entry_notional, \
            position_size_coin, \
            cumulative_funding
        if position == 0 or not entry_price:
            return
        close_price = float(price)
        if position == 1:
            gross_pnl = float(position_size_coin * (close_price - entry_price))
        else:
            gross_pnl = float(position_size_coin * (entry_price - close_price))
        exit_cost = float(entry_notional * fee_rate)
        net_pnl = float(gross_pnl - exit_cost - cumulative_funding)
        cash = float(cash + gross_pnl - exit_cost - cumulative_funding)
        side = "LONG" if position == 1 else "SHORT"
        return_pct = float((gross_pnl / entry_notional * 100) if entry_notional else 0.0)
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
                "fees": round(float(entry_notional * fee_rate * 2), 2),
                "fundingCost": round(float(cumulative_funding), 2),
                "netPnl": round(net_pnl, 2),
                "returnPct": round(return_pct, 2),
            }
        )
        position = 0
        entry_price = 0.0
        entry_time = None
        entry_notional = 0.0
        position_size_coin = 0.0
        cumulative_funding = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        price = row["close"]
        time = df.index[i]
        signal = int(row["signal"])

        # Funding cost for holding the position through this bar.
        if position != 0 and entry_notional:
            funding_cost = float(position * entry_notional * row.get("fundingRate", 0.0))
            cash = float(cash - funding_cost)
            cumulative_funding = float(cumulative_funding + funding_cost)

        if signal != position:
            if position != 0:
                close_position(price, time)
            if signal != 0:
                open_position(signal, price, time)

        mark_equity(price, time)

    # Close any open position at the final close.
    if position != 0:
        close_position(df["close"].iloc[-1], df.index[-1])

    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else float(cash)
    total_return = float(
        (final_equity - initial_balance) / initial_balance * 100 if initial_balance else 0.0
    )
    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    benchmark_return = float((last_close / first_close - 1) * 100 if first_close else 0.0)

    equity_values = [float(pt["equity"]) for pt in equity_curve]
    equity_returns = pd.Series(equity_values).pct_change().dropna()
    sharpe = 0.0
    if not equity_returns.empty and equity_returns.std() > 1e-9:
        sharpe = float(
            (equity_returns.mean() / equity_returns.std())
            * np.sqrt(_annualization_factor(interval))
        )
        sharpe = max(-50.0, min(50.0, sharpe))

    max_dd = float(max([pt["drawdown"] for pt in drawdown_curve]) if drawdown_curve else 0.0)

    wins = [t for t in trades if t["netPnl"] > 0]
    losses = [t for t in trades if t["netPnl"] <= 0]
    win_rate = float((len(wins) / len(trades) * 100) if trades else 0.0)
    gross_profit = float(sum(t["grossPnl"] for t in wins))
    gross_loss = float(abs(sum(t["grossPnl"] for t in losses)))
    profit_factor = float(
        gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
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

    summary = {
        "initialBalance": _fmt(initial_balance),
        "finalBalance": _fmt(final_equity),
        "totalReturnPct": _fmt(total_return),
        "benchmarkReturnPct": _fmt(benchmark_return),
        "sharpeRatio": _fmt(sharpe),
        "maxDrawdownPct": _fmt(max_dd),
        "winRatePct": _fmt(win_rate),
        "profitFactor": _fmt(profit_factor) if not math.isinf(float(profit_factor)) else 999.99,
        "totalTrades": int(len(trades)),
        "avgTradeReturnPct": _fmt(avg_trade_return),
        "avgWinPct": _fmt(avg_win),
        "avgLossPct": _fmt(avg_loss),
        "startTime": df.index[0].isoformat(),
        "endTime": df.index[-1].isoformat(),
        "interval": interval,
        "symbol": symbol,
        "strategyName": strategy.get("name", ""),
    }

    return {
        "summary": summary,
        "equity": equity_curve,
        "drawdown": drawdown_curve,
        "trades": trades,
        "monthlyReturns": monthly_returns,
    }
