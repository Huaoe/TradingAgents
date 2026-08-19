"""Protective-exit calculations shared by paper monitoring and tests."""

from __future__ import annotations

from typing import Any


def protective_levels(
    entry_price: float,
    side: str,
    risk_config: dict[str, Any] | None,
) -> dict[str, float | None]:
    """Resolve fixed protective levels from an actual fill price."""
    config = risk_config or {}
    # RiskConfig stores decimal fractions (0.02 means 2%), matching backtest.py.
    stop_pct = float(config.get("stopLossPct") or 0.0)
    target_pct = float(config.get("takeProfitPct") or 0.0)
    trailing_pct = float(config.get("trailingStopPct") or 0.0)
    is_long = side in {"Buy", "LONG"}
    return {
        "stopPrice": (
            entry_price * (1 - stop_pct)
            if stop_pct > 0 and is_long
            else entry_price * (1 + stop_pct)
            if stop_pct > 0
            else None
        ),
        "takeProfitPrice": (
            entry_price * (1 + target_pct)
            if target_pct > 0 and is_long
            else entry_price * (1 - target_pct)
            if target_pct > 0
            else None
        ),
        "trailingStopPct": trailing_pct if trailing_pct > 0 else None,
        "trailingWatermark": entry_price,
    }


def evaluate_protective_exit(
    position: dict[str, Any],
    mark_price: float,
    *,
    opening_tick: bool = False,
) -> dict[str, Any]:
    """Advance the watermark and evaluate one mark-price protective tick."""
    side = position.get("side", "Buy")
    is_long = side in {"Buy", "LONG"}
    watermark = float(position.get("trailingWatermark") or position["entryPrice"])
    result: dict[str, Any] = {
        "watermark": watermark,
        "reason": None,
        "triggerPrice": None,
    }
    if opening_tick:
        return result

    stop_price = position.get("stopPrice")
    target_price = position.get("takeProfitPrice")
    trailing_pct = float(position.get("trailingStopPct") or 0.0)
    trailing_price = (
        watermark * (1 - trailing_pct)
        if is_long and trailing_pct > 0
        else watermark * (1 + trailing_pct)
        if trailing_pct > 0
        else None
    )
    candidates = [
        ("stop_loss", float(stop_price)) if stop_price is not None else None,
        ("trailing_stop", trailing_price) if trailing_price is not None else None,
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    candidates.sort(key=lambda candidate: candidate[1], reverse=is_long)
    for reason, candidate in candidates:
        if (is_long and mark_price <= candidate) or (
            not is_long and mark_price >= candidate
        ):
            result.update({"reason": reason, "triggerPrice": candidate})
            return result

    if target_price is not None and (
        (is_long and mark_price >= float(target_price))
        or (not is_long and mark_price <= float(target_price))
    ):
        result.update({"reason": "take_profit", "triggerPrice": float(target_price)})
        return result

    result["watermark"] = max(watermark, mark_price) if is_long else min(watermark, mark_price)
    return result
