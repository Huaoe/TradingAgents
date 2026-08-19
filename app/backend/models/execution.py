"""Pydantic models for trade execution."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    """Payload for executing a persisted signal."""

    signalId: str
    walletId: str
    mode: Literal["paper", "live"] = "paper"
    masterPassword: str | None = None


class ClosePositionRequest(BaseModel):
    """Payload for closing an open position."""

    walletId: str
    positionId: str | None = None
    mode: Literal["paper", "live"] = "paper"
    masterPassword: str | None = None


class OrderRecord(BaseModel):
    """A stored order."""

    id: str
    signalId: str | None
    walletId: str
    symbol: str
    side: str
    size: float
    price: float
    notional: float
    leverage: int
    fees: float
    mode: str
    status: str
    timestamp: str
    meta: dict[str, Any] | None = None


class PositionRecord(BaseModel):
    """A stored position."""

    id: str
    orderId: str
    walletId: str
    symbol: str
    side: str
    entryPrice: float
    markPrice: float
    size: float
    notional: float
    leverage: int
    pnl: float
    pnlPct: float
    liquidationPrice: float | None
    margin: float
    status: str
    mode: Literal["paper", "live"] = "paper"
    pnlSource: Literal["exchange", "mark_price"] = "mark_price"
    openedAt: str
    closedAt: str | None
