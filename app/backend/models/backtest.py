"""Pydantic models for backtest requests and results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel


class BacktestRequest(BaseModel):
    """Payload for running a historical simulation."""

    symbol: str
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    startAt: str  # ISO-8601 date/datetime
    endAt: str
    strategyId: str | None = None
    strategy: dict[str, Any] | None = None
    initialBalance: float = 10_000.0
    makerFee: float = 0.0002
    takerFee: float = 0.00045
    slippagePct: float = 0.0005
    orderType: Literal["maker", "taker"] = "taker"


class TradeRecord(BaseModel):
    """One completed round-trip trade."""

    entryTime: str
    exitTime: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    entryPrice: float
    exitPrice: float
    sizeCoin: float
    notional: float
    leverage: int
    grossPnl: float
    fees: float
    fundingCost: float
    netPnl: float
    returnPct: float
    confidence: int
    exitReason: Literal["signal", "stop_loss", "take_profit", "trailing_stop", "end_of_backtest"]


class BacktestSummary(BaseModel):
    """Headline statistics displayed at the top of the backtest page."""

    initialBalance: float
    finalBalance: float
    totalReturnPct: float
    benchmarkReturnPct: float
    sharpeRatio: float
    maxDrawdownPct: float
    winRatePct: float
    profitFactor: float
    totalTrades: int
    avgTradeReturnPct: float
    avgWinPct: float
    avgLossPct: float
    avgConfidence: float = 0.0
    avgSignalConfidence: float = 0.0
    confidenceFloor: int = 60
    leverage: int = 3
    allocation: float = 0.10
    finalSignal: int = 0
    longSignals: int = 0
    shortSignals: int = 0
    flatSignals: int = 0
    startTime: str
    endTime: str
    interval: str
    symbol: str
    strategyName: str = ""
    makerFee: float = 0.0002
    takerFee: float = 0.00045
    slippagePct: float = 0.0005
    orderType: Literal["maker", "taker"] = "taker"
    totalGrossPnl: float = 0.0
    totalFees: float = 0.0
    totalFundingCost: float = 0.0


class BacktestResult(BaseModel):
    """Full backtest response."""

    summary: BacktestSummary
    equity: list[dict[str, Any]]
    drawdown: list[dict[str, Any]]
    price: list[dict[str, Any]]
    trades: list[TradeRecord]
    monthlyReturns: dict[str, float] | None = None

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
