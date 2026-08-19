"""Pydantic models for portfolio and risk settings."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    """Aggregated portfolio metrics for the dashboard."""

    walletId: str | None
    mode: str
    balanceSource: str
    balance: float
    available: float
    marginUsed: float
    unrealizedPnl: float
    dailyPnl: float
    totalValue: float
    totalNotional: float
    openPositions: int
    maxExposureSymbol: str
    maxExposureNotional: float
    maxLeverage: int
    llmSpend: float = 0.0
    llmTokensIn: int = 0
    llmTokensOut: int = 0
    llmCalls: int = 0


class LiveModeRequest(BaseModel):
    """Toggle live trading for a wallet."""

    walletId: str
    enabled: bool
