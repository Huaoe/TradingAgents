"""Tests for execution safety gates and live exchange setup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.execution_engine import ExecutionEngine, _set_live_leverage


def test_live_execution_requires_global_gate(monkeypatch, isolated_stores, mock_hyperliquid_client):
    engine = ExecutionEngine()
    monkeypatch.delenv("LIVE_TRADING", raising=False)

    with pytest.raises(ValueError, match="Global live trading gate is off"):
        engine._require_live_gates("wallet-test")


def test_live_execution_requires_wallet_gate(monkeypatch, isolated_stores, mock_hyperliquid_client):
    engine = ExecutionEngine()
    monkeypatch.setenv("LIVE_TRADING", "true")

    with pytest.raises(ValueError, match="Wallet live trading gate is off"):
        engine._require_live_gates("wallet-test")


def test_live_exchange_uses_configured_network(monkeypatch):
    captured = {}

    class FakeExchange:
        def __init__(self, account, base_url, account_address):
            captured.update(
                {"account": account, "base_url": base_url, "account_address": account_address}
            )

    monkeypatch.setattr("hyperliquid.exchange.Exchange", FakeExchange)
    monkeypatch.setattr("eth_account.Account.from_key", lambda key: "account")
    monkeypatch.setenv("HYPERLIQUID_NETWORK", "mainnet")

    from backend.services.execution_engine import _live_exchange
    from backend.services.hyperliquid_config import get_hyperliquid_base_url

    exchange = _live_exchange(SimpleNamespace(address="0xabc"), "private-key")

    assert isinstance(exchange, FakeExchange)
    assert captured == {
        "account": "account",
        "base_url": get_hyperliquid_base_url("mainnet"),
        "account_address": "0xabc",
    }


def test_live_leverage_update_rejects_exchange_failure():
    class FakeExchange:
        def update_leverage(self, leverage, symbol, is_cross):
            return {"status": "err", "response": "rejected"}

    with pytest.raises(ValueError, match="Could not set BTC leverage to 5x"):
        _set_live_leverage(FakeExchange(), "BTC", 5)
