"""Tests for execution safety gates and live exchange setup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import backend.services.execution_engine as execution_engine_module
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


def test_live_close_uses_exchange_fills_and_funding(monkeypatch, isolated_stores, mock_hyperliquid_client):
    position = {
        "id": "pos-live",
        "orderId": "ord-live",
        "walletId": "wallet-live",
        "symbol": "BTC",
        "side": "Buy",
        "entryPrice": 100.0,
        "markPrice": 100.0,
        "size": 1.0,
        "notional": 100.0,
        "leverage": 2,
        "pnl": 0.0,
        "pnlPct": 0.0,
        "liquidationPrice": None,
        "margin": 50.0,
        "status": "open",
        "mode": "live",
        "openedAt": "2024-01-01T00:00:00+00:00",
        "closedAt": None,
    }
    order = {
        "id": "ord-live",
        "meta": {"actualFee": 0.5},
        "status": "filled",
    }

    class FakeStore:
        def get_position(self, position_id: str) -> dict:
            return position

        def get_order(self, order_id: str) -> dict:
            return order

        def update_position(self, updated: dict) -> dict:
            return updated

        def update_order(self, updated: dict) -> dict:
            return updated

    class FakeExchange:
        def market_close(self, symbol: str, size: float) -> dict:
            return {
                "status": "ok",
                "response": {
                    "data": {
                        "statuses": [{"filled": {"oid": 2, "avgPx": "110"}}],
                    }
                },
            }

    mock_hyperliquid_client.fills = [
        {
            "oid": 2,
            "px": "110",
            "sz": "1",
            "fee": "0.6",
            "builderFee": "0.1",
            "closedPnl": "10",
        },
    ]
    mock_hyperliquid_client.user_funding = [{"coin": "BTC", "usdc": "-0.4"}]
    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
        decrypt_private_key=lambda wallet_id, password: "private-key",
    )
    engine.portfolio_engine = SimpleNamespace(
        portfolio_store=SimpleNamespace(is_live_enabled=lambda wallet_id: True),
    )
    engine.alert_engine = SimpleNamespace(
        execution_divergence=lambda *args: None,
        position_closed=lambda *args: None,
        journal_closed_trade=lambda *args: None,
    )
    monkeypatch.setattr(engine, "_require_live_gates", lambda wallet_id: None)
    monkeypatch.setattr(execution_engine_module, "_live_exchange", lambda wallet, key: FakeExchange())

    result = engine.close_position(
        "pos-live",
        "wallet-live",
        mode="live",
        master_password="password",
    )

    assert result["netPnl"] == pytest.approx(8.4)
    assert order["meta"]["costSource"] == "exchange_fills"
    assert order["meta"]["actualFee"] == pytest.approx(1.2)
    assert order["meta"]["fundingPaid"] == pytest.approx(0.4)
    assert order["meta"]["netPnlBasis"] == "exchangeClosedPnl - fees - funding"


def test_live_unrealized_pnl_uses_exchange_position(mock_hyperliquid_client):
    engine = ExecutionEngine()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    mock_hyperliquid_client.clearinghouse["assetPositions"] = [
        {
            "position": {
                "coin": "BTC",
                "szi": "1",
                "positionValue": "105",
                "unrealizedPnl": "5.25",
            }
        }
    ]
    position = {
        "walletId": "wallet-live",
        "symbol": "BTC",
        "mode": "live",
        "entryPrice": 100.0,
        "markPrice": 100.0,
        "notional": 100.0,
        "pnl": 0.0,
        "pnlPct": 0.0,
    }

    engine._compute_live_pnl(position)

    assert position["markPrice"] == pytest.approx(105.0)
    assert position["pnl"] == pytest.approx(5.25)
    assert position["pnlSource"] == "exchange"
