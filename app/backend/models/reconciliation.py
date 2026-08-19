"""API models for exchange reconciliation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ReconcileRequest(BaseModel):
    walletId: str


class ReconciliationResult(BaseModel):
    id: str
    walletId: str
    timestamp: str
    status: Literal["ok", "diverged", "unavailable", "not_applicable"]
    divergences: list[dict[str, Any]]
    error: str | None = None
