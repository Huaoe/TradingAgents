"""Tests for the shared template signal scoring and feature preparation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.template_signals import (
    _rsi,
    prepare_candles_features,
    signal_for_bar,
)


@pytest.fixture
def default_risk_config():
    return {
        "longFundingThreshold": -0.0005,
        "shortFundingThreshold": 0.0005,
        "leverage": 3,
        "allocation": 0.10,
        "confidenceFloor": 60,
    }


def _build_candle_df(closes):
    from backend.tests.conftest import make_candles

    return prepare_candles_features(make_candles(closes))


def test_prepare_candles_features_returns_expected_columns():
    closes = list(range(100, 200))
    df = _build_candle_df(closes)
    expected = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "return",
        "sma20",
        "sma50",
        "std20",
        "upperBB",
        "lowerBB",
        "rsi14",
        "atr14",
        "atrSma20",
        "donchianHigh",
        "donchianLow",
        "dtHH",
        "dtHC",
        "dtLC",
        "dtLL",
        "emaHigh",
        "emaLow",
        "emaSlow",
        "tsmomRet",
    }
    assert expected.issubset(set(df.columns))
    assert not df.empty


def _assert_close_or_nan(actual, expected):
    if pd.isna(actual) and pd.isna(expected):
        return
    assert np.isclose(actual, expected, equal_nan=True)


def test_rolling_indicators_are_shifted_to_avoid_look_ahead():
    closes = [100.0 + i + 5.0 * np.sin(i / 5.0) for i in range(120)]
    df = _build_candle_df(closes)

    for i in range(1, len(df)):
        close_window = df["close"].iloc[max(0, i - 20) : i]
        expected_sma20 = close_window.mean() if i >= 20 else float("nan")
        _assert_close_or_nan(df["sma20"].iloc[i], expected_sma20)

        close_window50 = df["close"].iloc[max(0, i - 50) : i]
        expected_sma50 = close_window50.mean() if i >= 50 else float("nan")
        _assert_close_or_nan(df["sma50"].iloc[i], expected_sma50)

        if i >= 20:
            std = close_window.std(ddof=1)
            _assert_close_or_nan(df["std20"].iloc[i], std)
            _assert_close_or_nan(
                df["upperBB"].iloc[i], df["sma20"].iloc[i] + 2 * std
            )
            _assert_close_or_nan(
                df["lowerBB"].iloc[i], df["sma20"].iloc[i] - 2 * std
            )

            high_window = df["high"].iloc[max(0, i - 20) : i]
            low_window = df["low"].iloc[max(0, i - 20) : i]
            _assert_close_or_nan(df["donchianHigh"].iloc[i], high_window.max())
            _assert_close_or_nan(df["donchianLow"].iloc[i], low_window.min())

        dt_high = df["high"].iloc[max(0, i - 4) : i]
        dt_low = df["low"].iloc[max(0, i - 4) : i]
        expected_dt_hh = dt_high.max() if i >= 4 else float("nan")
        expected_dt_ll = dt_low.min() if i >= 4 else float("nan")
        _assert_close_or_nan(df["dtHH"].iloc[i], expected_dt_hh)
        _assert_close_or_nan(df["dtLL"].iloc[i], expected_dt_ll)

        if i > 2:
            expected_rsi = _rsi(df["close"].iloc[:i], 14).iloc[-1]
            _assert_close_or_nan(df["rsi14"].iloc[i], expected_rsi)


def test_signal_for_bar_trend_following(default_risk_config):
    closes = [100.0 + i for i in range(100)]
    df = _build_candle_df(closes)
    strategy = {"template": "trend_following", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, len(df) - 1, strategy)
    assert sig == 1
    assert conf >= 70


def test_funding_arb_uses_shifted_relative_extremes_with_absolute_fallback():
    df = pd.DataFrame(
        {
            "close": [100.0, 100.0, 100.0],
            "sma20": [100.0, 100.0, 100.0],
            "sma50": [100.0, 100.0, 100.0],
            "rsi14": [50.0, 50.0, 50.0],
            "upperBB": [110.0, 110.0, 110.0],
            "lowerBB": [90.0, 90.0, 90.0],
            "fundingRate": [-2.0, 2.0, 0.00002],
            "fundingMedian168": [np.nan, 0.0, 0.0],
            "fundingStd168": [np.nan, 1.0, np.nan],
        }
    )
    strategy = {
        "template": "funding_rate_arb",
        "riskConfig": {
            "longFundingThreshold": -0.000002,
            "shortFundingThreshold": 0.000011,
            "fundingExtremeK": 1.5,
        },
    }

    assert signal_for_bar(df, 1, strategy) == (-1, 20)
    assert signal_for_bar(df, 2, strategy) == (-1, 20)
    df.loc[1, "fundingRate"] = -2.0
    assert signal_for_bar(df, 1, strategy) == (1, 80)


def test_signal_for_bar_momentum_breakout(default_risk_config):
    # 80 bars flat, small ramp, final explosion above the upper Bollinger band.
    closes = [100.0] * 81 + [100.0 + (i - 80) * 2.0 for i in range(81, 99)] + [180.0]
    df = _build_candle_df(closes)
    strategy = {"template": "momentum_breakout", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, len(df) - 1, strategy)
    assert sig == 1
    assert conf >= 70


def test_signal_for_bar_mean_reversion(default_risk_config):
    # Sudden crash to well below the lower Bollinger band with a low RSI.
    closes = [100.0] * 98 + [50.0, 50.0]
    df = _build_candle_df(closes)
    strategy = {"template": "mean_reversion", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, len(df) - 1, strategy)
    assert sig == 1
    assert conf >= 70


def test_signal_for_bar_basis_arbitrage(default_risk_config):
    closes = [100.0] * 60
    df = _build_candle_df(closes)
    df["fundingRate"] = -0.001
    strategy = {"template": "basis_arbitrage", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, 50, strategy)
    assert sig == 1
    assert conf == 80


def test_signal_for_bar_custom(default_risk_config):
    closes = [100.0 + i for i in range(100)]
    df = _build_candle_df(closes)
    # Negative funding adds a contrarian long score to the trend.
    df["fundingRate"] = -0.001
    strategy = {"template": "custom", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, len(df) - 1, strategy)
    assert sig == 1
    assert conf >= 60


def test_signal_for_bar_returns_flat_at_insufficient_history(default_risk_config):
    closes = [100.0] * 10
    df = _build_candle_df(closes)
    strategy = {"template": "trend_following", "riskConfig": default_risk_config}
    sig, conf = signal_for_bar(df, 5, strategy)
    assert sig == 0
    assert conf == 0
