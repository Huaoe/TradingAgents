"""Tests for the historical backtest engine."""

from __future__ import annotations

import pytest

from backend.services.backtest import _sharpe_ratio, run_backtest


@pytest.fixture
def trend_strategy():
    return {
        "name": "Trend",
        "template": "trend_following",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    }


def test_run_backtest_returns_expected_summary_and_curves(mock_hyperliquid_client, trend_strategy):
    mock_hyperliquid_client.candles = [
        {"time": 1_704_067_200_000 + i * 3_600_000, "open": 100.0 + i, "high": 101.0 + i,
         "low": 99.0 + i, "close": 100.0 + i, "volume": 1_000.0, "symbol": "BTC", "interval": "1h"}
        for i in range(100)
    ]

    result = run_backtest(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-31",
        strategy=trend_strategy,
    )

    assert "summary" in result
    assert "equity" in result
    assert "drawdown" in result
    assert "price" in result
    assert "trades" in result
    assert "monthlyReturns" in result

    summary = result["summary"]
    for key in [
        "initialBalance",
        "finalBalance",
        "totalReturnPct",
        "benchmarkReturnPct",
        "sharpeRatio",
        "maxDrawdownPct",
        "winRatePct",
        "profitFactor",
        "totalTrades",
        "avgTradeReturnPct",
        "avgWinPct",
        "avgLossPct",
        "confidenceFloor",
        "leverage",
        "allocation",
        "finalSignal",
        "longSignals",
        "shortSignals",
        "flatSignals",
        "startTime",
        "endTime",
        "interval",
        "symbol",
        "strategyName",
    ]:
        assert key in summary

    assert len(result["price"]) > 0
    for point in result["price"]:
        assert "time" in point
        assert "close" in point

    for trade in result["trades"]:
        assert "confidence" in trade
        assert isinstance(trade["confidence"], int)


def test_run_backtest_price_and_trade_confidence_populated(mock_hyperliquid_client, trend_strategy):
    mock_hyperliquid_client.candles = [
        {"time": 1_704_067_200_000 + i * 3_600_000, "open": 100.0 + i, "high": 101.0 + i,
         "low": 99.0 + i, "close": 100.0 + i, "volume": 1_000.0, "symbol": "BTC", "interval": "1h"}
        for i in range(100)
    ]

    result = run_backtest(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-31",
        strategy=trend_strategy,
    )

    assert all("time" in p and "close" in p for p in result["price"])
    assert all("confidence" in t and t["confidence"] >= 0 for t in result["trades"])


def test_sharpe_ratio_edge_cases():
    assert _sharpe_ratio([], "1h") == 0.0
    assert _sharpe_ratio([10_000.0], "1h") == 0.0
    assert _sharpe_ratio([10_000.0, 10_000.0, 10_000.0], "1h") == 0.0
    assert _sharpe_ratio([10_000.0, 10_001.0], "1h") == 0.0

    rising = [10_000.0 + i for i in range(100)]
    assert _sharpe_ratio(rising, "1h") > 0.0

    falling = [10_000.0 - i for i in range(100)]
    assert _sharpe_ratio(falling, "1h") < 0.0

    # Values that would produce an extreme Sharpe should be clamped.
    huge_jump = [1.0, 1_000_000.0]
    assert abs(_sharpe_ratio(huge_jump, "1h")) <= 50.0

    # NaN/inf in equity should fall back to 0.0.
    assert _sharpe_ratio([float("nan"), 1.0, 2.0], "1h") == 0.0
