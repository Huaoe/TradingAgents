"""Pydantic models for signal requests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SignalCreate(BaseModel):
    """Payload for generating and storing a new signal."""

    symbol: str
    strategy: dict[str, Any] | None = None
    strategyId: str | None = None
    useLlm: bool = False
