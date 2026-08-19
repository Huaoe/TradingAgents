"""Shared Hyperliquid network configuration."""

from __future__ import annotations

import os

from hyperliquid.utils import constants

NETWORK_ENV_VAR = "HYPERLIQUID_NETWORK"
DEFAULT_NETWORK = "testnet"


def get_hyperliquid_network(network: str | None = None) -> str:
    """Resolve the configured Hyperliquid network, defaulting safely to testnet."""
    value = (network or os.getenv(NETWORK_ENV_VAR, DEFAULT_NETWORK)).strip().lower()
    if value not in {"mainnet", "testnet"}:
        raise ValueError(f"{NETWORK_ENV_VAR} must be 'mainnet' or 'testnet', got {value!r}")
    return value


def get_hyperliquid_base_url(network: str | None = None) -> str:
    """Return the SDK API URL for the configured network."""
    return (
        constants.MAINNET_API_URL
        if get_hyperliquid_network(network) == "mainnet"
        else constants.TESTNET_API_URL
    )
