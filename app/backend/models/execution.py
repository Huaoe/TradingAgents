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
    orderType: Literal["market", "limit"] = "market"
    limitPrice: float | None = None
    tif: Literal["Alo", "Gtc", "Ioc"] = "Alo"
    expireMinutes: float | None = None


class ClosePositionRequest(BaseModel):
    """Payload for closing an open position."""

    walletId: str
    positionId: str | None = None
    mode: Literal["paper", "live"] = "paper"
    masterPassword: str | None = None


class CancelOrderRequest(BaseModel):
    """Cancel one resting order."""

    walletId: str
    symbol: str
    orderId: str
    masterPassword: str | None = None


class KillSwitchRequest(BaseModel):
    """Flatten one wallet mode and disable its live gate."""

    walletId: str
    mode: Literal["paper", "live"] = "live"
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
    type: str = "Market"
    limitPrice: float | None = None
    tif: str | None = None
    filledSize: float = 0.0
    expiresAt: str | None = None
    exchangeOrderId: str | None = None
    updatedAt: str | None = None
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
    stopPrice: float | None = None
    takeProfitPrice: float | None = None
    trailingStopPct: float | None = None
    trailingWatermark: float | None = None
    exitReason: str | None = None
    protectiveStatus: str = "disabled"
    exchangeStopOrderId: str | None = None
    exchangeTakeProfitOrderId: str | None = None
    trailingUnsupported: bool = False
    openedAt: str
    closedAt: str | None
