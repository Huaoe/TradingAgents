"""Pydantic models for alerts and trade journal."""

from __future__ import annotations

from pydantic import BaseModel


class AlertReadRequest(BaseModel):
    """Request to mark an alert as read."""

    read: bool = True
