"""Tests for the historical backtest engine."""

from __future__ import annotations

import pandas as pd
import pytest

import backend.services.backtest as backtest_module
from backend.services.backtest import _merge_funding, _sharpe_ratio, run_backtest


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
        {
            "time": 1_704_067_200_000 + i * 3_600_000,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 1_000.0,
            "symbol": "BTC",
            "interval": "1h",
        }
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
        {
            "time": 1_704_067_200_000 + i * 3_600_000,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 1_000.0,
            "symbol": "BTC",
            "interval": "1h",
        }
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


def _scripted_backtest(
    monkeypatch,
    mock_hyperliquid_client,
    signals,
    prices,
    confidences=None,
    highs=None,
    lows=None,
    funding=None,
    interval="1h",
    risk_config=None,
    **kwargs,
):
    confidences = confidences or [80 if signal else 50 for signal in signals]
    highs = highs or prices
    lows = lows or prices
    step_ms = {
        "5m": 5 * 60_000,
        "15m": 15 * 60_000,
        "1h": 60 * 60_000,
    }[interval]
    start_ms = 1_704_067_200_000
    mock_hyperliquid_client.candles = [
        {
            "time": start_ms + i * step_ms,
            "open": price,
            "high": highs[i],
            "low": lows[i],
            "close": price,
            "volume": 1_000.0,
            "symbol": "BTC",
            "interval": interval,
        }
        for i, price in enumerate(prices)
    ]
    mock_hyperliquid_client.funding = funding or []

    def scripted_signals(df, strategy):
        return pd.DataFrame(
            {"signal": signals, "confidence": confidences},
            index=df.index,
        )

    monkeypatch.setattr(backtest_module, "_compute_signals", scripted_signals)
    config = {
        "template": "custom",
        "riskConfig": {
            "leverage": 1,
            "allocation": 1.0,
            "confidenceFloor": 60,
            **(risk_config or {}),
        },
    }
    return run_backtest(
        "BTC",
        interval,
        "2024-01-01",
        "2024-01-03",
        strategy=config,
        initial_balance=10_000.0,
        **kwargs,
    )


def test_fee_side_and_exit_notional_fee(monkeypatch, mock_hyperliquid_client):
    taker = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 0],
        [100.0, 110.0],
        taker_fee=0.01,
        slippage_pct=0.0,
        maker_fee=0.002,
        order_type="taker",
    )
    maker = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 0],
        [100.0, 110.0],
        taker_fee=0.01,
        slippage_pct=0.0,
        maker_fee=0.002,
        order_type="maker",
    )

    assert taker["trades"][0]["fees"] == 210.0
    assert taker["trades"][0]["netPnl"] == 790.0
    assert maker["trades"][0]["fees"] == 42.0
    assert maker["trades"][0]["netPnl"] == 958.0


def test_min_hold_cooldown_and_exit_hysteresis(monkeypatch, mock_hyperliquid_client):
    result = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 0, 0, -1, 1, 0],
        [100.0] * 6,
        confidences=[80, 50, 50, 20, 80, 50],
        risk_config={
            "minHoldBars": 2,
            "cooldownBars": 2,
            "exitHysteresis": 50,
        },
        maker_fee=0.0,
        taker_fee=0.0,
        slippage_pct=0.0,
    )

    assert len(result["trades"]) == 1
    assert result["trades"][0]["exitReason"] == "signal"
    assert result["trades"][0]["exitTime"].endswith("03:00:00+00:00")


def test_stop_loss_wins_when_stop_and_target_are_both_hit(monkeypatch, mock_hyperliquid_client):
    result = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 1],
        [100.0, 100.0],
        highs=[100.0, 110.0],
        lows=[100.0, 90.0],
        risk_config={"stopLossPct": 0.05, "takeProfitPct": 0.05},
        maker_fee=0.0,
        taker_fee=0.0,
        slippage_pct=0.0,
    )

    trade = result["trades"][0]
    assert trade["exitReason"] == "stop_loss"
    assert trade["exitPrice"] == 95.0
    assert trade["grossPnl"] == -500.0


def test_take_profit_and_trailing_stop_exits(monkeypatch, mock_hyperliquid_client):
    target = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 1],
        [100.0, 100.0],
        highs=[100.0, 106.0],
        lows=[100.0, 101.0],
        risk_config={"takeProfitPct": 0.05},
        maker_fee=0.0,
        taker_fee=0.0,
        slippage_pct=0.0,
    )
    trailing = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 1, 1],
        [100.0, 100.0, 100.0],
        highs=[100.0, 110.0, 109.0],
        lows=[100.0, 108.0, 103.0],
        risk_config={"trailingStopPct": 0.05},
        maker_fee=0.0,
        taker_fee=0.0,
        slippage_pct=0.0,
    )

    assert target["trades"][0]["exitReason"] == "take_profit"
    assert target["trades"][0]["exitPrice"] == 105.0
    assert trailing["trades"][0]["exitReason"] == "trailing_stop"
    assert trailing["trades"][0]["exitPrice"] == 104.5


def test_funding_scales_with_bar_duration(monkeypatch, mock_hyperliquid_client):
    start_ms = 1_704_067_200_000
    result = _scripted_backtest(
        monkeypatch,
        mock_hyperliquid_client,
        [1, 1],
        [100.0, 100.0],
        interval="15m",
        funding=[{"time": start_ms, "fundingRate": 0.01, "premium": 0.0}],
        maker_fee=0.0,
        taker_fee=0.0,
        slippage_pct=0.0,
    )

    assert result["trades"][0]["fundingCost"] == 25.0


def test_merge_funding_does_not_backfill_leading_gaps():
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    df = pd.DataFrame(index=[start, start + pd.Timedelta(hours=1)])
    merged = _merge_funding(
        df,
        [{"time": int((start + pd.Timedelta(hours=1)).timestamp() * 1000), "fundingRate": 0.01}],
    )

    assert merged["fundingRate"].tolist() == [0.0, 0.01]
