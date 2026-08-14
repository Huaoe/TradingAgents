"""Pydantic models for trading strategies."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RiskConfig(BaseModel):
    """Risk parameters passed to the signal engine."""

    longFundingThreshold: float = -0.0005
    shortFundingThreshold: float = 0.0005
    leverage: int = 3
    allocation: float = 0.10
    confidenceFloor: int = 60


class StrategyBase(BaseModel):
    """Editable fields for a strategy."""

    name: str
    description: str = ""
    template: str = "custom"
    markets: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=lambda: ["Market", "Funding", "OrderBook"])
    llmProvider: str = "glm"
    llmModel: str = "glm-5-turbo"
    llmMode: Literal["quick", "deep"] = "quick"
    executionMode: Literal["manual", "auto-confirm", "auto"] = "manual"
    schedule: str = ""
    riskConfig: RiskConfig = Field(default_factory=RiskConfig)


class StrategyCreate(StrategyBase):
    """Payload for creating a new strategy."""


class StrategyUpdate(BaseModel):
    """Payload for editing an existing strategy."""

    name: str | None = None
    description: str | None = None
    template: str | None = None
    markets: list[str] | None = None
    agents: list[str] | None = None
    llmProvider: str | None = None
    llmModel: str | None = None
    llmMode: Literal["quick", "deep"] | None = None
    executionMode: Literal["manual", "auto-confirm", "auto"] | None = None
    schedule: str | None = None
    riskConfig: RiskConfig | None = None


class Strategy(StrategyBase):
    """Full stored strategy."""

    id: str
    createdAt: str
    updatedAt: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
