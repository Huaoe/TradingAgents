"""Pydantic models for background strategy searches."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class StrategySearchRequest(BaseModel):
    """Configuration for a walk-forward parameter search."""

    symbol: str
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    startAt: str
    endAt: str
    templates: list[str] | None = None
    folds: int = Field(default=4, ge=2, le=6)
    minTradesIS: int = Field(default=5, ge=0)
    gridPreset: Literal["standard", "coarse"] = "standard"
    initialBalance: float = 10_000.0
    makerFee: float = 0.00015
    takerFee: float = 0.00045
    slippagePct: float = 0.00005
    orderType: Literal["maker", "taker"] = "taker"
    feeSource: Literal["generic_default", "wallet", "manual"] = "generic_default"
    slippageSource: Literal["default", "live_book"] = "default"


class StrategySearchProgress(BaseModel):
    """Completed and total simulation counts for a search job."""

    completed: int
    total: int


class StrategySearchJob(BaseModel):
    """Status payload returned for a strategy search job."""

    id: str
    status: Literal["queued", "running", "done", "error"]
    candidateCount: int
    simulationCount: int
    progress: StrategySearchProgress
    result: dict[str, Any] | None = None
    error: str | None = None
