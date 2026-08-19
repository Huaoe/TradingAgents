"""Tests for the live signal engine."""

from __future__ import annotations

import pytest

from backend.services.signal_engine import _build_signal
from backend.services.template_signals import prepare_candles_features


@pytest.fixture
def trend_strategy():
    return {
        "template": "trend_following",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    }


@pytest.fixture
def custom_strategy():
    return {
        "template": "custom",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    }


def _uptrend_candles(count: int = 100):
    return [
        {"time": 1_704_067_200_000 + i * 3_600_000, "open": 100.0 + i, "high": 101.0 + i,
         "low": 99.0 + i, "close": 100.0 + i, "volume": 1_000.0, "symbol": "BTC", "interval": "1h"}
        for i in range(count)
    ]


def test_build_signal_returns_action_and_confidence_for_template(
    mock_hyperliquid_client, trend_strategy
):
    mock_hyperliquid_client.candles = _uptrend_candles()
    signal = _build_signal("BTC", trend_strategy)

    assert signal["action"] in ("BUY", "SELL", "HOLD")
    assert isinstance(signal["confidence"], int)
    assert 0 <= signal["confidence"] <= 100
    assert signal["symbol"] == "BTC"


def test_build_signal_template_uses_same_scoring_as_backtest(
    mock_hyperliquid_client, trend_strategy
):
    """The last-bar score from the shared signal_for_bar must match the live signal."""
    candles = _uptrend_candles()
    mock_hyperliquid_client.candles = candles

    df = prepare_candles_features(candles)
    df["fundingRate"] = 0.0
    idx = len(df) - 1

    from backend.services.template_signals import signal_for_bar

    expected_action, expected_conf = signal_for_bar(df, idx, trend_strategy)

    signal = _build_signal("BTC", trend_strategy)
    action_map = {1: "BUY", -1: "SELL", 0: "HOLD"}
    assert signal["action"] == action_map[expected_action]
    assert signal["confidence"] == expected_conf


def test_build_signal_returns_action_and_confidence_for_custom(
    mock_hyperliquid_client, custom_strategy
):
    mock_hyperliquid_client.candles = _uptrend_candles()
    # Push the custom rule engine into a clear BUY state.
    mock_hyperliquid_client.market["funding"] = -0.001
    mock_hyperliquid_client.orderbook["imbalance"] = 0.6

    signal = _build_signal("BTC", custom_strategy)

    assert signal["action"] == "BUY"
    assert isinstance(signal["confidence"], int)
    assert 0 <= signal["confidence"] <= 100


def test_build_signal_records_effective_risk_config(
    mock_hyperliquid_client, custom_strategy
):
    signal = _build_signal(
        "BTC",
        {
            **custom_strategy,
            "name": "audited",
            "maxOpenPositions": 2,
            "llmModel": "secret-model-name",
        },
    )

    risk_config = signal["meta"]["riskConfig"]
    assert risk_config["stopLossPct"] is None
    assert risk_config["leverage"] == 3
    assert risk_config["maxOpenPositions"] == 2
    assert "name" not in risk_config
    assert "llmModel" not in risk_config
    assert signal["meta"]["strategyTemplate"] == "custom"
