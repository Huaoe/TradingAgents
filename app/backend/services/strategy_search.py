"""Walk-forward parameter search for built-in strategy templates."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pandas as pd

from backend.services.backtest import (
    _annualization_factor,
    _simulate_backtest,
    attach_signals,
    load_backtest_frame,
)
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.search_stats import (
    annualise_sharpe,
    deflated_sharpe_ratio,
    label_regimes,
    per_bar_returns,
    per_bar_sharpe,
    rank_correlation,
    summarise_trades_by_regime,
)
from backend.services.strategy_store import TEMPLATES

WORK_BUDGET = 30_000_000
_PROTECTIVE_TRIPLES = [
    (0.0, 0.0, 0.0),
    (0.01, 0.02, 0.0),
    (0.02, 0.04, 0.0),
    (0.0, 0.0, 0.015),
]
_COARSE_PROTECTIVE_TRIPLES = _PROTECTIVE_TRIPLES[:2]
ProgressCallback = Callable[[int, int], None]


def _grid_values(grid_preset: str) -> tuple[list[int], list[int], list[int], list[tuple[float, float, float]]]:
    if grid_preset == "standard":
        return [55, 60, 65, 70, 75], [0, 2, 4], [0, 3], _PROTECTIVE_TRIPLES
    if grid_preset == "coarse":
        return [60, 70], [0, 4], [0], _COARSE_PROTECTIVE_TRIPLES
    raise ValueError(f"Unknown grid preset: {grid_preset}")


def resolve_templates(template_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Resolve request selectors against the built-in template catalog."""
    if not template_names:
        return deepcopy(TEMPLATES)

    resolved = []
    for selector in template_names:
        selector_lower = selector.lower()
        matches = [
            template
            for template in TEMPLATES
            if selector_lower
            in {
                str(template["id"]).lower(),
                str(template["template"]).lower(),
                str(template["name"]).lower(),
            }
        ]
        if not matches:
            raise ValueError(f"Unknown built-in template: {selector}")
        resolved.append(deepcopy(matches[0]))
    return resolved


def build_candidate_grid(
    templates: list[dict[str, Any]],
    grid_preset: str = "standard",
) -> list[dict[str, Any]]:
    """Build the exact candidate grid for each selected template."""
    confidence_floors, min_holds, cooldowns, protective_triples = _grid_values(grid_preset)
    candidates: list[dict[str, Any]] = []
    for template in templates:
        base_risk = deepcopy(template.get("riskConfig") or {})
        candidate_index = 0
        for confidence_floor in confidence_floors:
            for min_hold in min_holds:
                for cooldown in cooldowns:
                    for stop_loss, take_profit, trailing_stop in protective_triples:
                        risk = {
                            **base_risk,
                            "confidenceFloor": confidence_floor,
                            "minHoldBars": min_hold,
                            "cooldownBars": cooldown,
                            "stopLossPct": stop_loss,
                            "takeProfitPct": take_profit,
                            "trailingStopPct": trailing_stop,
                        }
                        strategy = {**deepcopy(template), "riskConfig": risk}
                        candidates.append(
                            {
                                "id": f"{template['template']}:{candidate_index}",
                                "template": template["template"],
                                "strategy": strategy,
                                "overrides": {
                                    "confidenceFloor": confidence_floor,
                                    "minHoldBars": min_hold,
                                    "cooldownBars": cooldown,
                                    "stopLossPct": stop_loss,
                                    "takeProfitPct": take_profit,
                                    "trailingStopPct": trailing_stop,
                                },
                            }
                        )
                        candidate_index += 1
    return candidates


def split_walk_forward_blocks(
    frame: pd.DataFrame,
    folds: int,
) -> list[pd.DataFrame]:
    """Split a frame into K+1 deterministic, contiguous, disjoint blocks."""
    if folds < 2 or folds > 6:
        raise ValueError("folds must be between 2 and 6")
    if len(frame) < folds + 1:
        raise ValueError("not enough bars for the requested walk-forward folds")
    block_count = folds + 1
    base_size, remainder = divmod(len(frame), block_count)
    sizes = [base_size + (1 if i < remainder else 0) for i in range(block_count)]
    boundaries = [0]
    for size in sizes:
        boundaries.append(boundaries[-1] + size)
    return [frame.iloc[boundaries[i] : boundaries[i + 1]].copy() for i in range(folds + 1)]


def walk_forward_splits(
    frame: pd.DataFrame,
    folds: int,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Return anchored train and disjoint test slices for each fold."""
    blocks = split_walk_forward_blocks(frame, folds)
    return [
        (pd.concat(blocks[:fold], axis=0), blocks[fold])
        for fold in range(1, folds + 1)
    ]


def simulation_count(candidate_count: int, folds: int) -> int:
    return candidate_count * (2 * folds + 1)


def validate_work_budget(bar_count: int, candidate_count: int, folds: int) -> int:
    total = bar_count * simulation_count(candidate_count, folds)
    if total > WORK_BUDGET:
        raise ValueError(
            f"Search exceeds the work budget of {WORK_BUDGET:,} bar-simulations "
            f"({total:,} requested); try fewer templates, a shorter range, or the coarse preset"
        )
    return total


def _signal_cache_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    risk = candidate["strategy"].get("riskConfig") or {}
    return (
        candidate["template"],
        risk.get("confidenceFloor"),
        risk.get("longFundingThreshold"),
        risk.get("shortFundingThreshold"),
        risk.get("fundingExtremeK"),
    )


def _score(
    result: dict[str, Any],
    interval: str,
    *,
    include_returns: bool = False,
) -> dict[str, Any]:
    equity = [float(point["equity"]) for point in result.get("equity", [])]
    returns = per_bar_returns(equity)
    sharpe = per_bar_sharpe(returns)
    summary = result.get("summary") or {}
    trades = int(summary.get("totalTrades", len(result.get("trades", []))))
    if trades == 0 and sharpe is None:
        sharpe = 0.0
    annualised = (
        annualise_sharpe(sharpe, _annualization_factor(interval)) if sharpe is not None else None
    )
    score = {
        "perBarSharpe": sharpe,
        "annualisedSharpe": annualised,
        "returnPct": float(summary.get("totalReturnPct", 0.0)),
        "benchmarkReturnPct": float(summary.get("benchmarkReturnPct", 0.0)),
        "trades": trades,
        "maxDrawdownPct": float(summary.get("maxDrawdownPct", 0.0)),
    }
    if include_returns:
        score["returns"] = returns
    return score


def _public_score(score: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in score.items() if key != "returns"}


def _finite_score(value: float | None) -> float:
    return value if value is not None and math.isfinite(value) else float("-inf")


def _simulate_candidate(
    frame: pd.DataFrame,
    candidate: dict[str, Any],
    *,
    symbol: str,
    interval: str,
    initial_balance: float,
    maker_fee: float,
    taker_fee: float,
    slippage_pct: float,
    order_type: str,
    fee_source: str,
    slippage_source: str,
    max_leverage: int,
    include_price: bool = True,
) -> dict[str, Any]:
    return _simulate_backtest(
        frame,
        symbol=symbol,
        interval=interval,
        strategy=candidate["strategy"],
        initial_balance=initial_balance,
        maker_fee=maker_fee,
        taker_fee=taker_fee,
        slippage_pct=slippage_pct,
        order_type=order_type,
        fee_source=fee_source,
        slippage_source=slippage_source,
        max_leverage=max_leverage,
        include_price=include_price,
    )


def prepare_strategy_search(
    symbol: str,
    interval: str,
    start_at: str,
    end_at: str,
    templates: list[str] | None = None,
    folds: int = 4,
    grid_preset: str = "standard",
) -> tuple[pd.DataFrame, int, list[dict[str, Any]], int]:
    """Load the frame and validate a search before registering its job."""
    selected_templates = resolve_templates(templates)
    candidates = build_candidate_grid(selected_templates, grid_preset)
    client = HyperliquidClient()
    frame = load_backtest_frame(symbol, interval, start_at, end_at, client=client)
    market = client.get_market(symbol) or {}
    max_leverage = int(market.get("maxLeverage") or 3)
    validate_work_budget(len(frame), len(candidates), folds)
    return frame, max_leverage, candidates, simulation_count(len(candidates), folds)


def run_strategy_search(
    *,
    symbol: str,
    interval: str,
    start_at: str,
    end_at: str,
    templates: list[str] | None = None,
    folds: int = 4,
    min_trades_is: int = 5,
    grid_preset: str = "standard",
    initial_balance: float = 10_000.0,
    maker_fee: float = 0.00015,
    taker_fee: float = 0.00045,
    slippage_pct: float = 0.00005,
    order_type: str = "taker",
    fee_source: str = "generic_default",
    slippage_source: str = "default",
    progress: ProgressCallback | None = None,
    prepared_frame: pd.DataFrame | None = None,
    prepared_max_leverage: int | None = None,
) -> dict[str, Any]:
    """Run the configured walk-forward search over one loaded frame."""
    if min_trades_is < 0:
        raise ValueError("minTradesIS must be non-negative")
    selected_templates = resolve_templates(templates)
    candidates = build_candidate_grid(selected_templates, grid_preset)
    if prepared_frame is None:
        frame, max_leverage, _, total = prepare_strategy_search(
            symbol,
            interval,
            start_at,
            end_at,
            templates,
            folds,
            grid_preset,
        )
    else:
        frame = prepared_frame
        max_leverage = prepared_max_leverage or 3
        validate_work_budget(len(frame), len(candidates), folds)
        total = simulation_count(len(candidates), folds)

    if progress:
        progress(0, total)

    signal_cache: dict[tuple[Any, ...], pd.DataFrame] = {}
    for candidate in candidates:
        key = _signal_cache_key(candidate)
        if key not in signal_cache:
            signal_cache[key] = attach_signals(frame, candidate["strategy"])

    splits = walk_forward_splits(frame, folds)
    signal_slices: dict[
        tuple[Any, ...], tuple[pd.DataFrame, list[tuple[pd.DataFrame, pd.DataFrame]]]
    ] = {}
    for key, signal_frame in signal_cache.items():
        signal_slices[key] = (
            signal_frame,
            [
                (signal_frame.loc[train.index], signal_frame.loc[test.index])
                for train, test in splits
            ],
        )
    candidate_records: dict[str, dict[str, Any]] = {
        candidate["id"]: {
            "candidateId": candidate["id"],
            "template": candidate["template"],
            "overrides": candidate["overrides"],
            "folds": [],
            "full": None,
        }
        for candidate in candidates
    }
    completed = 0
    simulation_lock = threading.Lock()

    def run_simulation(
        candidate: dict[str, Any],
        data: pd.DataFrame,
        *,
        retain_full: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
        nonlocal completed
        result = _simulate_candidate(
            data,
            candidate,
            symbol=symbol,
            interval=interval,
            initial_balance=initial_balance,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            slippage_pct=slippage_pct,
            order_type=order_type,
            fee_source=fee_source,
            slippage_source=slippage_source,
            max_leverage=max_leverage,
            include_price=False,
        )
        score = _score(result, interval, include_returns=retain_full)
        trades = result.get("trades", []) if retain_full else None
        with simulation_lock:
            completed += 1
            if progress:
                progress(completed, total)
        return score, trades

    for candidate in candidates:
        record = candidate_records[candidate["id"]]
        signal_frame, fold_slices = signal_slices[_signal_cache_key(candidate)]
        for fold_number, (train, test) in enumerate(fold_slices, start=1):
            train_score, _ = run_simulation(candidate, train)
            test_score, _ = run_simulation(candidate, test)
            record["folds"].append(
                {
                    "fold": fold_number,
                    "inSample": train_score,
                    "outOfSample": test_score,
                }
            )
        full_score, full_trades = run_simulation(candidate, signal_frame, retain_full=True)
        record["full"] = {"score": full_score, "trades": full_trades or []}

    selected_folds = []
    skipped_folds = []
    selected_oos_returns: list[float] = []
    buy_hold_returns: list[float] = []
    for fold_number in range(1, folds + 1):
        eligible = [
            record
            for record in candidate_records.values()
            if record["folds"][fold_number - 1]["inSample"]["trades"] >= min_trades_is
        ]
        if not eligible:
            skipped_folds.append(
                {
                    "fold": fold_number,
                    "trainStart": splits[fold_number - 1][0].index[0].isoformat(),
                    "trainEnd": splits[fold_number - 1][0].index[-1].isoformat(),
                    "testStart": splits[fold_number - 1][1].index[0].isoformat(),
                    "testEnd": splits[fold_number - 1][1].index[-1].isoformat(),
                    "reason": f"No candidate reached minTradesIS={min_trades_is}",
                }
            )
            continue
        selected = max(
            eligible,
            key=lambda record: (
                _finite_score(record["folds"][fold_number - 1]["inSample"]["perBarSharpe"]),
                record["folds"][fold_number - 1]["inSample"]["trades"],
                -record["folds"][fold_number - 1]["inSample"]["maxDrawdownPct"],
            ),
        )
        selected_fold = selected["folds"][fold_number - 1]
        selected_oos = selected_fold["outOfSample"]
        selected_oos_returns.append(selected_oos["returnPct"] / 100.0)
        buy_hold_returns.append(selected_oos["benchmarkReturnPct"] / 100.0)
        selected_folds.append(
            {
                "fold": fold_number,
                "trainStart": splits[fold_number - 1][0].index[0].isoformat(),
                "trainEnd": splits[fold_number - 1][0].index[-1].isoformat(),
                "testStart": splits[fold_number - 1][1].index[0].isoformat(),
                "testEnd": splits[fold_number - 1][1].index[-1].isoformat(),
                "candidateId": selected["candidateId"],
                "template": selected["template"],
                "overrides": selected["overrides"],
                "inSample": _public_score(selected_fold["inSample"]),
                "outOfSample": _public_score(selected_oos),
            }
        )

    candidate_summaries = []
    for record in candidate_records.values():
        folds_data = record["folds"]

        def fold_sharpe(score: dict[str, Any]) -> float:
            value = score["perBarSharpe"]
            if score["trades"] == 0 or value is None or not math.isfinite(value):
                return 0.0
            return float(value)

        is_sharpes = [fold_sharpe(fold["inSample"]) for fold in folds_data]
        oos_sharpes = [fold_sharpe(fold["outOfSample"]) for fold in folds_data]
        oos_returns = [fold["outOfSample"]["returnPct"] for fold in folds_data]
        valid_is = [float(value) for value in is_sharpes]
        valid_oos = [float(value) for value in oos_sharpes]
        full_score = record["full"]["score"]
        candidate_summaries.append(
            {
                "candidateId": record["candidateId"],
                "template": record["template"],
                "overrides": record["overrides"],
                "riskConfig": next(
                    candidate["strategy"]["riskConfig"]
                    for candidate in candidates
                    if candidate["id"] == record["candidateId"]
                ),
                "meanInSampleSharpePerBar": float(pd.Series(valid_is).mean()) if valid_is else None,
                "meanOutOfSampleSharpePerBar": float(pd.Series(valid_oos).mean()) if valid_oos else None,
                "medianOutOfSampleSharpePerBar": float(pd.Series(valid_oos).median())
                if valid_oos
                else None,
                "medianOutOfSampleSharpeAnnualised": (
                    annualise_sharpe(
                        float(pd.Series(valid_oos).median()),
                        _annualization_factor(interval),
                    )
                    if valid_oos
                    else None
                ),
                "meanInSampleSharpeAnnualised": (
                    annualise_sharpe(float(pd.Series(valid_is).mean()), _annualization_factor(interval))
                    if valid_is
                    else None
                ),
                "meanOutOfSampleSharpeAnnualised": (
                    annualise_sharpe(float(pd.Series(valid_oos).mean()), _annualization_factor(interval))
                    if valid_oos
                    else None
                ),
                "meanOutOfSampleReturnPct": float(pd.Series(oos_returns).mean()),
                "medianOutOfSampleReturnPct": float(pd.Series(oos_returns).median()),
                "totalOutOfSampleTrades": sum(
                    fold["outOfSample"]["trades"] for fold in folds_data
                ),
                "foldsWithTrades": sum(
                    1 for fold in folds_data if fold["outOfSample"]["trades"] > 0
                ),
                "worstFold": min(
                    (
                        {
                            "fold": fold["fold"],
                            "returnPct": fold["outOfSample"]["returnPct"],
                            "perBarSharpe": fold["outOfSample"]["perBarSharpe"],
                        }
                        for fold in folds_data
                    ),
                    key=lambda item: item["returnPct"],
                ),
                "overfitGap": (
                    float(pd.Series(valid_is).mean()) - float(pd.Series(valid_oos).mean())
                    if valid_is and valid_oos
                    else None
                ),
                "overfitGapAnnualised": (
                    annualise_sharpe(
                        float(pd.Series(valid_is).mean()) - float(pd.Series(valid_oos).mean()),
                        _annualization_factor(interval),
                    )
                    if valid_is and valid_oos
                    else None
                ),
                "fullRange": {
                    "returnPct": full_score["returnPct"],
                    "trades": full_score["trades"],
                    "perBarSharpe": full_score["perBarSharpe"],
                    "annualisedSharpe": full_score["annualisedSharpe"],
                },
                "_meanInSample": float(pd.Series(valid_is).mean()),
                "_meanOutOfSample": float(pd.Series(valid_oos).mean()),
            }
        )

    candidate_summaries.sort(
        key=lambda item: _finite_score(item["medianOutOfSampleSharpePerBar"]),
        reverse=True,
    )
    rank_corr = rank_correlation(
        [item["_meanInSample"] for item in candidate_summaries],
        [item["_meanOutOfSample"] for item in candidate_summaries],
    )
    for item in candidate_summaries:
        item.pop("_meanInSample")
        item.pop("_meanOutOfSample")

    full_winner = max(
        candidates,
        key=lambda candidate: _finite_score(
            candidate_records[candidate["id"]]["full"]["score"]["perBarSharpe"]
        ),
    )
    full_record = candidate_records[full_winner["id"]]
    dsr = deflated_sharpe_ratio(
        full_record["full"]["score"]["returns"],
        [
            candidate_records[candidate["id"]]["full"]["score"]["perBarSharpe"]
            for candidate in candidates
        ],
    )

    regimes = label_regimes(frame)
    regime_candidates = candidate_summaries[:3] + [
        item for item in candidate_summaries if item["candidateId"] == full_winner["id"]
    ]
    regime_breakdown = []
    seen_ids: set[str] = set()
    for candidate_summary in regime_candidates:
        candidate_id = candidate_summary["candidateId"]
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        full_trades = candidate_records[candidate_id]["full"]["trades"]
        regime_breakdown.append(
            {
                "candidateId": candidate_id,
                "template": candidate_summary["template"],
                "regimes": summarise_trades_by_regime(full_trades, regimes),
            }
        )

    selection_return = (math.prod(1.0 + value for value in selected_oos_returns) - 1.0) * 100
    buy_hold_return = (math.prod(1.0 + value for value in buy_hold_returns) - 1.0) * 100
    return {
        "symbol": symbol,
        "interval": interval,
        "startAt": start_at,
        "endAt": end_at,
        "folds": folds,
        "minTradesIS": min_trades_is,
        "gridPreset": grid_preset,
        "candidateCount": len(candidates),
        "simulationCount": total,
        "selection": {
            "returnPct": selection_return,
            "buyAndHoldReturnPct": buy_hold_return,
            "foldsConsidered": len(selected_folds),
            "foldsSkipped": len(skipped_folds),
            "selectedFolds": selected_folds,
            "skippedFolds": skipped_folds,
        },
        "skippedFolds": skipped_folds,
        "candidates": candidate_summaries,
        "rankCorrelation": rank_corr,
        "fullRangeWinner": {
            "candidateId": full_winner["id"],
            "template": full_winner["template"],
            "overrides": full_winner["overrides"],
            "riskConfig": full_winner["strategy"]["riskConfig"],
            "returnPct": full_record["full"]["score"]["returnPct"],
            "trades": full_record["full"]["score"]["trades"],
            "perBarSharpe": full_record["full"]["score"]["perBarSharpe"],
            "annualisedSharpe": full_record["full"]["score"]["annualisedSharpe"],
        },
        "deflatedSharpeRatio": dsr,
        "regimeBreakdown": regime_breakdown,
    }
