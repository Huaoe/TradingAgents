"""Tests for walk-forward strategy search and search statistics."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

import backend.main as main_module
import backend.services.search_stats as stats_module
import backend.services.strategy_search as search_module
from backend.services.search_stats import (
    deflated_sharpe_ratio,
    label_regimes,
    rank_correlation,
    summarise_trades_by_regime,
)


def _frame(rows: int = 36) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series(np.linspace(100, 110, rows), index=index)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
            "fundingRate": 0.0,
            "fundingEvents": [[] for _ in range(rows)],
        },
        index=index,
    )


def _fake_result(frame: pd.DataFrame, trades: int = 5, strong: bool = False) -> dict:
    values = [10_000.0, 10_010.0, 10_005.0, 10_020.0]
    if strong:
        values = [10_000.0, 10_200.0, 10_050.0, 10_300.0]
    trade_rows = [
        {
            "entryTime": frame.index[0].isoformat(),
            "netPnl": 1.0,
            "returnPct": 0.01,
        }
        for _ in range(trades)
    ]
    return {
        "equity": [{"time": frame.index[i].isoformat(), "equity": value} for i, value in enumerate(values)],
        "trades": trade_rows,
        "summary": {
            "totalReturnPct": (values[-1] / values[0] - 1) * 100,
            "benchmarkReturnPct": 1.0,
            "totalTrades": trades,
            "maxDrawdownPct": 1.0,
        },
    }


def test_grid_sizes_and_walk_forward_blocks_are_deterministic():
    template = {
        "id": "template-test",
        "name": "Test",
        "template": "trend_following",
        "riskConfig": {},
    }
    assert len(search_module.build_candidate_grid([template], "standard")) == 120
    assert len(search_module.build_candidate_grid([template], "coarse")) == 8

    frame = _frame(11)
    blocks = search_module.split_walk_forward_blocks(frame, 4)
    assert len(blocks) == 5
    assert sum(len(block) for block in blocks) == len(frame)
    assert [block.index[0] for block in blocks] == [
        frame.index[0],
        frame.index[3],
        frame.index[5],
        frame.index[7],
        frame.index[9],
    ]
    assert [block.index[-1] for block in blocks] == [
        frame.index[2],
        frame.index[4],
        frame.index[6],
        frame.index[8],
        frame.index[10],
    ]
    splits = search_module.walk_forward_splits(frame, 4)
    assert splits[0][0].index.equals(frame.index[:3])
    assert splits[0][1].index.equals(frame.index[3:5])
    assert splits[-1][0].index.equals(frame.index[:9])
    assert splits[-1][1].index.equals(frame.index[9:])


def test_signal_cache_is_once_per_distinct_signal_key(monkeypatch):
    frame = _frame()
    calls = 0

    def fake_attach(data, strategy):
        nonlocal calls
        calls += 1
        return data.assign(signal=0, confidence=50)

    monkeypatch.setattr(search_module, "attach_signals", fake_attach)
    monkeypatch.setattr(
        search_module,
        "_simulate_candidate",
        lambda data, candidate, **kwargs: _fake_result(data),
    )
    result = search_module.run_strategy_search(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-03",
        templates=["trend_following"],
        folds=2,
        grid_preset="standard",
        prepared_frame=frame,
        prepared_max_leverage=5,
    )
    assert calls == 5
    assert result["candidateCount"] == 120
    assert result["simulationCount"] == 600


def test_ineligible_high_sharpe_candidate_is_not_selected(monkeypatch):
    frame = _frame()

    monkeypatch.setattr(
        search_module,
        "attach_signals",
        lambda data, strategy: data.assign(signal=0, confidence=50),
    )

    def fake_simulate(data, candidate, **kwargs):
        is_ineligible = candidate["id"].endswith(":0")
        return _fake_result(data, trades=1 if is_ineligible else 5, strong=is_ineligible)

    monkeypatch.setattr(search_module, "_simulate_candidate", fake_simulate)
    result = search_module.run_strategy_search(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-03",
        templates=["trend_following"],
        folds=2,
        min_trades_is=5,
        grid_preset="coarse",
        prepared_frame=frame,
        prepared_max_leverage=5,
    )
    assert all(not fold["candidateId"].endswith(":0") for fold in result["selection"]["selectedFolds"])
    selected_fold = result["selection"]["selectedFolds"][0]
    assert selected_fold["trainStart"] == frame.index[0].isoformat()
    assert selected_fold["trainEnd"] == frame.index[11].isoformat()
    assert selected_fold["testStart"] == frame.index[12].isoformat()
    assert selected_fold["testEnd"] == frame.index[23].isoformat()


def test_no_trade_fold_scores_zero_and_curves_are_not_retained(monkeypatch):
    frame = _frame()
    include_price_values = []

    monkeypatch.setattr(
        search_module,
        "attach_signals",
        lambda data, strategy: data.assign(signal=0, confidence=50),
    )

    def fake_simulate(data, candidate, **kwargs):
        include_price_values.append(kwargs["include_price"])
        no_trades = candidate["id"].endswith(":0") and data.index[0] == frame.index[9]
        result = _fake_result(data, trades=0 if no_trades else 5)
        result["drawdown"] = [{"drawdown": 1.0}]
        result["price"] = [{"close": 100.0}]
        return result

    monkeypatch.setattr(search_module, "_simulate_candidate", fake_simulate)
    result = search_module.run_strategy_search(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-03",
        templates=["trend_following"],
        folds=3,
        grid_preset="coarse",
        prepared_frame=frame,
        prepared_max_leverage=5,
    )
    candidate = next(item for item in result["candidates"] if item["candidateId"].endswith(":0"))
    assert candidate["foldsWithTrades"] == 2
    assert candidate["medianOutOfSampleSharpePerBar"] > candidate["meanOutOfSampleSharpePerBar"]
    assert include_price_values and all(value is False for value in include_price_values)
    assert all("equity" not in item for item in result["candidates"])
    assert all("drawdown" not in item for item in result["candidates"])
    assert all("price" not in item for item in result["candidates"])


def test_fold_without_eligible_candidate_is_skipped(monkeypatch):
    frame = _frame()

    monkeypatch.setattr(
        search_module,
        "attach_signals",
        lambda data, strategy: data.assign(signal=0, confidence=50),
    )

    def fake_simulate(data, candidate, **kwargs):
        first_training_block = data.index[-1] == frame.index[11]
        return _fake_result(data, trades=0 if first_training_block else 5)

    monkeypatch.setattr(search_module, "_simulate_candidate", fake_simulate)
    result = search_module.run_strategy_search(
        symbol="BTC",
        interval="1h",
        start_at="2024-01-01",
        end_at="2024-01-03",
        templates=["trend_following"],
        folds=2,
        min_trades_is=5,
        grid_preset="coarse",
        prepared_frame=frame,
        prepared_max_leverage=5,
    )
    assert result["skippedFolds"] == [
        {
            "fold": 1,
            "trainStart": frame.index[0].isoformat(),
            "trainEnd": frame.index[11].isoformat(),
            "testStart": frame.index[12].isoformat(),
            "testEnd": frame.index[23].isoformat(),
            "reason": "No candidate reached minTradesIS=5",
        }
    ]
    assert result["selection"]["skippedFolds"] == result["skippedFolds"]
    assert len(result["selection"]["selectedFolds"]) == 1


def test_work_budget_rejects_large_search():
    with pytest.raises(ValueError, match="coarse preset"):
        search_module.validate_work_budget(30_000, 120, 4)


def test_search_job_endpoint_lifecycle(monkeypatch, test_client):
    frame = _frame(12)
    candidate = {"id": "trend_following:0"}
    monkeypatch.setattr(
        main_module,
        "prepare_strategy_search",
        lambda *args: (frame, 5, [candidate], 5),
    )

    def fake_run(**kwargs):
        kwargs["progress"](5, 5)
        return {"ok": True}

    monkeypatch.setattr(main_module, "run_strategy_search", fake_run)
    with main_module._SEARCH_JOBS_LOCK:
        main_module._SEARCH_JOBS.clear()
    response = test_client.post(
        "/api/strategy-search",
        json={
            "symbol": "BTC",
            "startAt": "2024-01-01",
            "endAt": "2024-01-03",
            "templates": ["trend_following"],
            "folds": 2,
            "gridPreset": "coarse",
        },
    )
    assert response.status_code == 200
    job = response.json()
    assert job["candidateCount"] == 1
    assert job["simulationCount"] == 5

    for _ in range(50):
        status = test_client.get(f"/api/strategy-search/{job['id']}").json()
        if status["status"] == "done":
            break
        time.sleep(0.01)
    assert status["status"] == "done"
    assert status["progress"] == {"completed": 5, "total": 5}
    assert status["result"] == {"ok": True}


def test_search_job_work_budget_is_http_400(monkeypatch, test_client):
    monkeypatch.setattr(
        main_module,
        "prepare_strategy_search",
        lambda *args: (_ for _ in ()).throw(
            ValueError("Search exceeds the work budget; try the coarse preset")
        ),
    )
    response = test_client.post(
        "/api/strategy-search",
        json={
            "symbol": "BTC",
            "startAt": "2024-01-01",
            "endAt": "2024-01-03",
            "folds": 4,
        },
    )
    assert response.status_code == 400
    assert "coarse preset" in response.json()["detail"]


def test_search_stats_rank_correlation_and_degenerate_cases():
    assert rank_correlation([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8)
    assert rank_correlation([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert rank_correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert rank_correlation([1, 1, 1], [1, 2, 3]) is None

    assert deflated_sharpe_ratio([], [0.1, 0.2])["reason"] == (
        "not enough return observations to estimate a Sharpe ratio"
    )
    assert deflated_sharpe_ratio([0.1, 0.2, 0.3, 0.2], [0.1])["reason"] == (
        "need at least two trials with varying Sharpe ratios to deflate"
    )
    assert deflated_sharpe_ratio([0.1, 0.2, 0.3], [0.1, 0.2])["reason"] == (
        "need at least four return observations for skew and kurtosis"
    )


def test_search_stats_remaining_dsr_none_reasons(monkeypatch):
    monkeypatch.setattr(stats_module, "per_bar_sharpe", lambda returns: 0.1)
    monkeypatch.setattr(stats_module, "expected_max_sharpe", lambda sharpes: 0.01)
    undefined_moments = deflated_sharpe_ratio([float("nan")] * 4, [0.1, 0.2])
    assert undefined_moments["reason"] == "return distribution moments are undefined"

    original_series = stats_module.pd.Series

    class NegativeVarianceMoments:
        def __len__(self):
            return 4

        def skew(self):
            return 100.0

        def kurt(self):
            return -3.0

    monkeypatch.setattr(stats_module.pd, "Series", lambda *args, **kwargs: NegativeVarianceMoments())
    monkeypatch.setattr(stats_module, "per_bar_sharpe", lambda returns: 0.1)
    non_positive = deflated_sharpe_ratio([1.0, 2.0, 3.0, 4.0], [0.1, 0.2])
    assert non_positive["reason"] == "Sharpe ratio variance estimate is non-positive"

    monkeypatch.setattr(stats_module.pd, "Series", original_series)
    monkeypatch.setattr(stats_module, "per_bar_sharpe", lambda returns: 0.1)
    monkeypatch.setattr(stats_module, "expected_max_sharpe", lambda sharpes: float("nan"))
    undefined_statistic = deflated_sharpe_ratio([1.0, 2.0, 3.0, 4.0], [0.1, 0.2])
    assert undefined_statistic["reason"] == "deflated statistic is undefined"


def test_search_stats_dsr_regimes_and_trade_buckets():
    noise = [(-1.0) ** i * 0.001 for i in range(200)]
    noise_dsr = deflated_sharpe_ratio(noise, [0.01 + i * 0.001 for i in range(20)])
    assert noise_dsr["dsr"] is not None and noise_dsr["dsr"] < 0.95

    strong = [0.001 + (i % 5) * 0.00001 for i in range(200)]
    strong_dsr = deflated_sharpe_ratio(strong, [0.0001, 0.0002, 0.0003])
    assert strong_dsr["dsr"] is not None and strong_dsr["dsr"] >= 0.95

    frame = _frame(6)
    frame["fundingRate"] = [-1.0, -1.0, -1.0, -1.0, 100.0, 100.0]
    regimes = label_regimes(frame, window=2)
    assert regimes.iloc[4]["fundingRegime"] == "funding_negative"

    trades = [
        {"entryTime": frame.index[4].isoformat(), "netPnl": 10.0, "returnPct": 1.0},
        {"entryTime": frame.index[4].isoformat(), "netPnl": -5.0, "returnPct": -0.5},
    ]
    summary = summarise_trades_by_regime(trades, regimes, min_trades=3)
    assert summary[0]["trades"] == 2
    assert summary[0]["wins"] == 1
    assert summary[0]["netPnl"] == 5.0
    assert summary[0]["sufficient"] is False
