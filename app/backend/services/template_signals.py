"""Reusable template-specific signal scoring and feature preparation.

This module is shared between the backtest engine and the live signal generator
so that a backtested template produces the same directional output when it is
run against live market data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-style RSI using exponential moving averages."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average true range using the prior bar's close for gap measurements."""
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def prepare_candles_features(candles: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a feature DataFrame from OHLCV candle records.

    All rolling indicators derived from the current bar's close are shifted by
    one bar so that a signal at index ``i`` only uses information from bars
    ``0..i-1``.  Indicators that are already calculated from prior bars only
    (Donchian channels, Dual Thrust ranges, time-series momentum, etc.) are
    left unchanged.
    """
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.set_index("time").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df["return"] = df["close"].pct_change()

    # Close-derived rolling indicators: lag by one bar to avoid look-ahead bias.
    df["sma20"] = df["close"].rolling(20).mean().shift(1)
    df["sma50"] = df["close"].rolling(50).mean().shift(1)
    df["std20"] = df["close"].rolling(20).std().shift(1)
    df["upperBB"] = df["sma20"] + 2 * df["std20"]
    df["lowerBB"] = df["sma20"] - 2 * df["std20"]
    df["rsi14"] = _rsi(df["close"], 14).shift(1)

    # ATR and its slow average.  The raw ATR is shifted once, and the SMA of
    # ATR is computed from the shifted series so both only use prior bars.
    raw_atr = _atr(df, 14)
    df["atr14"] = raw_atr.shift(1)
    df["atrSma20"] = raw_atr.rolling(20).mean().shift(1)

    # Already-shifted / non-look-ahead inputs (must stay as-is).
    df["donchianHigh"] = df["high"].rolling(20).max().shift(1)
    df["donchianLow"] = df["low"].rolling(20).min().shift(1)

    dt_lookback = 4
    df["dtHH"] = df["high"].rolling(dt_lookback).max().shift(1)
    df["dtHC"] = df["close"].rolling(dt_lookback).max().shift(1)
    df["dtLC"] = df["close"].rolling(dt_lookback).min().shift(1)
    df["dtLL"] = df["low"].rolling(dt_lookback).min().shift(1)

    df["emaHigh"] = df["high"].ewm(span=34, adjust=False).mean()
    df["emaLow"] = df["low"].ewm(span=34, adjust=False).mean()
    df["emaSlow"] = df["close"].ewm(span=200, adjust=False).mean()

    tsmom_lookback = 60
    df["tsmomRet"] = (df["close"] / df["close"].shift(tsmom_lookback) - 1).shift(1)

    return df


def signal_for_bar(
    df: pd.DataFrame,
    idx: int,
    strategy: dict[str, Any],
) -> tuple[int, int]:
    """Return (signal, confidence) for the bar at ``idx``.

    Signal values are ``-1`` (short), ``0`` (flat), or ``1`` (long).  The
    confidence is an integer score from 0 to 100 that was used to make the
    directional decision.
    """
    row = df.iloc[idx]
    if idx == 0 or pd.isna(row["sma50"]):
        return 0, 0

    close = row["close"]
    prev_close = df["close"].iloc[idx - 1]
    sma20 = row["sma20"]
    sma50 = row["sma50"]
    rsi = row["rsi14"]
    upper = row["upperBB"]
    lower = row["lowerBB"]
    funding = row.get("fundingRate", 0.0)

    cfg = strategy.get("riskConfig") or {}
    long_thr = _safe_float(cfg.get("longFundingThreshold"), -0.000005)
    short_thr = _safe_float(cfg.get("shortFundingThreshold"), 0.000012)
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
            return 0, int(score)
        score += funding_score()
    elif template == "mean-reversion":
        if rsi_score() > 0 and bound_score() > 0:
            score = 80
        elif rsi_score() < 0 and bound_score() < 0:
            score = 20
        else:
            return 0, int(score)
        score += funding_score()
    elif template in ("funding-rate-arb", "hype-delta-neutral", "basis-arbitrage"):
        if funding < long_thr:
            score = 80
        elif funding > short_thr:
            score = 20
        else:
            return 0, int(score)
    elif template == "trend-following":
        if trend_up:
            score = 70
        elif trend_down:
            score = 30
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "scalp-momentum":
        if pd.notna(upper) and close > upper and trend_up:
            score = 80
        elif pd.notna(lower) and close < lower and trend_down:
            score = 20
        else:
            return 0, int(score)
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
                return 0, int(score)
            score += funding_score()
        else:
            return 0, int(score)
    elif template == "grid-trading":
        donchian_high = row.get("donchianHigh")
        donchian_low = row.get("donchianLow")
        if pd.isna(donchian_high) or pd.isna(donchian_low) or donchian_high == donchian_low:
            return 0, int(score)
        range_span = donchian_high - donchian_low
        position_in_range = (close - donchian_low) / range_span
        if position_in_range <= 0.2:
            score = 70
        elif position_in_range >= 0.8:
            score = 30
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "dual-thrust":
        hh, hc, lc, ll = row.get("dtHH"), row.get("dtHC"), row.get("dtLC"), row.get("dtLL")
        if pd.isna(hh) or pd.isna(hc) or pd.isna(lc) or pd.isna(ll):
            return 0, int(score)
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
            return 0, int(score)
        score += funding_score()
    elif template == "turtle-breakout":
        donchian_high = row.get("donchianHigh")
        donchian_low = row.get("donchianLow")
        if pd.isna(donchian_high) or pd.isna(donchian_low):
            return 0, int(score)
        if close > donchian_high:
            score = 75
        elif close < donchian_low:
            score = 25
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "ema-bands-trend-catch":
        ema_high = row.get("emaHigh")
        ema_low = row.get("emaLow")
        ema_slow = row.get("emaSlow")
        if pd.isna(ema_high) or pd.isna(ema_low) or pd.isna(ema_slow):
            return 0, int(score)
        if close > ema_high and close > ema_slow:
            score = 75
        elif close < ema_low and close < ema_slow:
            score = 25
        elif pd.notna(upper) and pd.notna(lower):
            prev_upper = df["upperBB"].iloc[idx - 1]
            prev_lower = df["lowerBB"].iloc[idx - 1]
            if pd.notna(prev_upper) and prev_close > prev_upper and close < upper and rsi > 70:
                score = 25
            elif pd.notna(prev_lower) and prev_close < prev_lower and close > lower and rsi < 30:
                score = 75
            else:
                return 0, int(score)
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "atr-rsi-combo":
        atr = row["atr14"]
        atr_sma = row.get("atrSma20")
        if pd.isna(atr) or pd.isna(atr_sma) or atr <= atr_sma:
            return 0, int(score)
        if rsi < 30:
            score = 80
        elif rsi > 70:
            score = 20
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "time-series-momentum":
        tsmom_ret = row.get("tsmomRet")
        if pd.isna(tsmom_ret):
            return 0, int(score)
        if tsmom_ret > 0:
            score = 70
        elif tsmom_ret < 0:
            score = 30
        else:
            return 0, int(score)
        score += funding_score()
    elif template == "overnight-seasonality-btc":
        hour = df.index[idx].hour
        if hour == 22 or hour == 23:
            score = 80
        else:
            return 0, int(score)
        score += funding_score()
    else:  # custom / fallback
        if trend_up:
            score += 15
        if trend_down:
            score -= 15
        score += rsi_score() + bound_score() + funding_score()

    if score >= confidence_floor:
        return 1, int(score)
    if score <= (100 - confidence_floor):
        return -1, int(score)
    return 0, int(score)
