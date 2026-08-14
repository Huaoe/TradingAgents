"""Pydantic models for Hyperliquid wallets."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WalletBase(BaseModel):
    """Editable wallet fields returned by the API."""

    name: str
    address: str = Field(..., min_length=10)
    chain: str = "hyperliquid"
    isDefault: bool = False


class WalletCreate(WalletBase):
    """Payload for creating a new wallet.

    The private key is encrypted with the master password before storage.
    The plaintext key is never persisted.
    """

    privateKey: str = Field(..., min_length=1)
    masterPassword: str = Field(..., min_length=8)


class WalletUpdate(BaseModel):
    """Payload for updating an existing wallet."""

    name: str | None = None
    isDefault: bool | None = None


class Wallet(WalletBase):
    """Full stored wallet (does not expose the plaintext private key)."""

    id: str
    encryptedKey: str
    createdAt: str
    updatedAt: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
