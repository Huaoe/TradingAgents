"""Tests for execution safety gates and live exchange setup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import backend.services.execution_engine as execution_engine_module
from backend.services.execution_engine import ExecutionEngine, _set_live_leverage
from backend.services.protective import evaluate_protective_exit, protective_levels


def test_protective_levels_match_backtest_decimal_percentages():
    levels = protective_levels(100.0, "Buy", {
        "stopLossPct": 0.02,
        "takeProfitPct": 0.04,
        "trailingStopPct": 0.01,
    })

    assert levels["stopPrice"] == pytest.approx(98.0)
    assert levels["takeProfitPrice"] == pytest.approx(104.0)
    assert levels["trailingWatermark"] == 100.0


def test_protective_evaluation_precedence_watermark_and_opening_tick():
    position = {
        "side": "Buy",
        "entryPrice": 100.0,
        "stopPrice": 98.0,
        "takeProfitPrice": 104.0,
        "trailingStopPct": 0.01,
        "trailingWatermark": 100.0,
    }

    assert evaluate_protective_exit(position, 98.0, opening_tick=True)["reason"] is None
    advanced = evaluate_protective_exit(position, 103.0)
    assert advanced["reason"] is None
    assert advanced["watermark"] == pytest.approx(103.0)

    triggered = evaluate_protective_exit(
        {**position, "trailingWatermark": advanced["watermark"]},
        101.9,
    )
    assert triggered["reason"] == "trailing_stop"
    assert triggered["triggerPrice"] == pytest.approx(101.97)


def test_short_watermark_only_advances_without_exit():
    position = {
        "side": "Sell",
        "entryPrice": 100.0,
        "stopPrice": 102.0,
        "takeProfitPrice": 96.0,
        "trailingStopPct": 0.01,
        "trailingWatermark": 100.0,
    }
    result = evaluate_protective_exit(position, 97.0)
    assert result["reason"] is None
    assert result["watermark"] == pytest.approx(97.0)


def test_paper_protective_close_records_trigger_and_releases_pnl(
    isolated_stores, mock_hyperliquid_client
):
    position = {
        "id": "pos-paper",
        "orderId": "ord-paper",
        "walletId": "wallet-paper",
        "symbol": "BTC",
        "side": "Buy",
        "entryPrice": 100.0,
        "markPrice": 98.0,
        "size": 1.0,
        "notional": 100.0,
        "leverage": 2,
        "pnl": 0.0,
        "pnlPct": 0.0,
        "liquidationPrice": None,
        "margin": 50.0,
        "status": "open",
        "mode": "paper",
        "protectiveStatus": "armed",
        "stopPrice": 98.0,
        "takeProfitPrice": None,
        "trailingStopPct": None,
        "trailingWatermark": 100.0,
        "exitReason": None,
        "openedAt": "2024-01-01T00:00:00+00:00",
        "closedAt": None,
    }
    order = {"id": "ord-paper", "meta": {}, "status": "filled"}
    released = []

    class FakeStore:
        def get_position(self, position_id):
            return position

        def get_order(self, order_id):
            return order

        def update_position(self, updated):
            return updated

        def update_order(self, updated):
            return updated

    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    engine.portfolio_engine = SimpleNamespace(
        release_pnl=lambda *args, **kwargs: released.append((args, kwargs)),
    )
    engine.alert_engine = SimpleNamespace(
        position_closed=lambda *args: None,
        journal_closed_trade=lambda *args: None,
    )

    result = engine.close_position(
        "pos-paper",
        "wallet-paper",
        mode="paper",
        exit_reason="stop_loss",
        theoretical_trigger_price=98.0,
    )

    assert result["position"]["exitReason"] == "stop_loss"
    assert order["meta"]["protectiveTriggerPrice"] == 98.0
    assert order["meta"]["protectiveFillPrice"] == result["position"]["markPrice"]
    assert released and released[0][0][1] == pytest.approx(result["netPnl"])


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


def test_live_protection_places_reduce_only_trigger_orders(
    monkeypatch, isolated_stores, mock_hyperliquid_client
):
    calls = []

    class FakeExchange:
        def order(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {
                "status": "ok",
                "response": {"data": {"statuses": [{"resting": {"oid": 10 + len(calls)}}]}},
            }

    class FakeStore:
        def update_position(self, position):
            return position

    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.alert_engine = SimpleNamespace(
        protective_unsupported=lambda *args: None,
        protective_unprotected=lambda *args: None,
    )
    position = {
        "id": "pos-live",
        "walletId": "wallet-live",
        "symbol": "BTC",
        "side": "Buy",
        "size": 1.5,
        "stopPrice": 98.0,
        "takeProfitPrice": 104.0,
        "trailingUnsupported": True,
    }

    engine._place_live_protection(position, FakeExchange())

    assert position["protectiveStatus"] == "armed"
    assert position["exchangeStopOrderId"] == "11"
    assert position["exchangeTakeProfitOrderId"] == "12"
    assert all(call[1]["reduce_only"] is True for call in calls)
    assert [call[0][4]["trigger"]["tpsl"] for call in calls] == ["sl", "tp"]


def test_live_protection_failure_marks_position_unprotected_without_flattening(
    isolated_stores, mock_hyperliquid_client
):
    class FakeExchange:
        def order(self, *args, **kwargs):
            raise RuntimeError("exchange unavailable")

    class FakeStore:
        def update_position(self, position):
            return position

    alerts = []
    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.alert_engine = SimpleNamespace(
        protective_unsupported=lambda *args: None,
        protective_unprotected=lambda *args: alerts.append(args),
    )
    position = {
        "id": "pos-live",
        "walletId": "wallet-live",
        "symbol": "BTC",
        "side": "Buy",
        "size": 1.0,
        "stopPrice": 98.0,
        "takeProfitPrice": 104.0,
        "trailingUnsupported": False,
    }

    engine._place_live_protection(position, FakeExchange())

    assert position["protectiveStatus"] == "unprotected"
    assert alerts


def test_kill_switch_continues_after_one_position_failure(
    monkeypatch, isolated_stores, mock_hyperliquid_client
):
    class FakeStore:
        def list_open_positions(self, wallet_id):
            return [
                {"id": "pos-1", "mode": "paper", "status": "open"},
                {"id": "pos-2", "mode": "paper", "status": "open"},
            ]

    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    engine.portfolio_engine = SimpleNamespace(
        portfolio_store=SimpleNamespace(
            set_live_enabled=lambda wallet_id, enabled: setattr(engine, "disabled", enabled),
        ),
    )
    engine.alert_engine = SimpleNamespace(kill_switch=lambda *args: None)
    calls = []

    def close(position_id, *args, **kwargs):
        calls.append(position_id)
        if position_id == "pos-1":
            raise RuntimeError("close failed")
        return {"position": {"id": position_id}}

    monkeypatch.setattr(engine, "close_position", close)
    result = engine.kill_switch("wallet-1", "paper")

    assert calls == ["pos-1", "pos-2"]
    assert [item["status"] for item in result["positions"]] == ["error", "closed"]
    assert result["liveEnabled"] is False
