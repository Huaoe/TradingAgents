"""Tests for execution safety gates and live exchange setup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import backend.services.execution_engine as execution_engine_module
from backend.services.execution_engine import ExecutionEngine, _set_live_leverage
from backend.services.execution_store import ExecutionStore
from backend.services.protective import evaluate_protective_exit, protective_levels


def _signal(signal_id: str = "sig-limit", action: str = "BUY") -> dict:
    return {
        "id": signal_id,
        "symbol": "BTC",
        "action": action,
        "confidence": 80,
        "size": 100.0,
        "entry": 100.0,
        "stop": 0.0,
        "target": 0.0,
        "leverage": 2,
        "reasoning": "test",
        "agents": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": {"riskConfig": {}},
    }


def _execution_engine_with_signal(
    signal: dict,
    mock_hyperliquid_client,
) -> ExecutionEngine:
    engine = ExecutionEngine()
    engine.signal_store.store_signal(signal)
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    engine.portfolio_engine = SimpleNamespace(
        can_open_position=lambda *args: None,
    )
    return engine


def test_limit_placement_rests_without_position(isolated_stores, mock_hyperliquid_client):
    engine = _execution_engine_with_signal(_signal(), mock_hyperliquid_client)

    result = engine.execute(
        "sig-limit",
        "wallet-paper",
        mode="paper",
        order_type="limit",
        limit_price=99.0,
    )

    assert result["position"] is None
    assert result["order"]["status"] == "resting"
    assert result["order"]["type"] == "Limit"
    assert result["order"]["limitPrice"] == 99.0
    assert ExecutionStore().list_open_positions() == []


def test_market_execution_still_fills_and_opens_position(
    isolated_stores, mock_hyperliquid_client
):
    engine = _execution_engine_with_signal(_signal("sig-market"), mock_hyperliquid_client)

    result = engine.execute("sig-market", "wallet-paper")

    assert result["order"]["type"] == "Market"
    assert result["order"]["status"] == "filled"
    assert result["position"]["status"] == "open"
    assert result["position"]["size"] == pytest.approx(1.0)


def test_paper_limit_fill_uses_maker_fee_at_limit(
    isolated_stores, mock_hyperliquid_client
):
    mock_hyperliquid_client.user_fees["userAddRate"] = "0.00010"
    mock_hyperliquid_client.user_fees["userCrossRate"] = "0.00090"
    engine = _execution_engine_with_signal(
        _signal("sig-maker"),
        mock_hyperliquid_client,
    )
    result = engine.execute(
        "sig-maker",
        "wallet-paper",
        order_type="limit",
        limit_price=99.0,
    )
    mock_hyperliquid_client.market["markPrice"] = 99.0
    mock_hyperliquid_client.market["price"] = 99.0

    engine.refresh_positions()

    order = ExecutionStore().get_order(result["order"]["id"])
    position = ExecutionStore().list_open_positions()[0]
    assert order is not None
    assert order["status"] == "filled"
    assert order["fees"] == pytest.approx(100.0 / 99.0 * 99.0 * 0.00010)
    assert order["fees"] != pytest.approx(100.0 * 0.00090)
    assert position["entryPrice"] == pytest.approx(99.0)
    assert order["meta"]["queueModelled"] is False


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_crossing_alo_limit_is_rejected(
    monkeypatch, isolated_stores, mock_hyperliquid_client, mode
):
    engine = _execution_engine_with_signal(_signal(f"sig-cross-{mode}"), mock_hyperliquid_client)
    monkeypatch.setattr(engine, "_require_live_gates", lambda wallet_id: None)

    with pytest.raises(ValueError, match="would cross"):
        engine.execute(
            f"sig-cross-{mode}",
            "wallet-test",
            mode=mode,
            order_type="limit",
            limit_price=101.0,
        )


def test_live_partial_fill_creates_position_and_keeps_order_pending(
    monkeypatch, isolated_stores, mock_hyperliquid_client
):
    class FakeExchange:
        def update_leverage(self, leverage, symbol, is_cross):
            return {"status": "ok"}

        def order(self, *args, **kwargs):
            return {
                "status": "ok",
                "response": {"data": {"statuses": [{"resting": {"oid": 77}}]}},
            }

    mock_hyperliquid_client.open_orders = [{"oid": 77, "coin": "BTC"}]
    mock_hyperliquid_client.fills = [
        {"oid": 77, "px": "99", "sz": "0.5", "fee": "0.01"}
    ]
    engine = _execution_engine_with_signal(_signal("sig-partial"), mock_hyperliquid_client)
    monkeypatch.setattr(engine, "_require_live_gates", lambda wallet_id: None)
    monkeypatch.setattr(
        execution_engine_module,
        "_live_exchange",
        lambda wallet, key: FakeExchange(),
    )
    engine.wallet_store.decrypt_private_key = lambda wallet_id, password: "private"

    result = engine.execute(
        "sig-partial",
        "wallet-live",
        mode="live",
        master_password="password",
        order_type="limit",
        limit_price=99.0,
    )
    engine.refresh_positions()

    order = ExecutionStore().get_order(result["order"]["id"])
    positions = ExecutionStore().list_open_positions()
    assert order is not None
    assert order["status"] == "partially_filled"
    assert order["filledSize"] == pytest.approx(0.5)
    assert positions[0]["size"] == pytest.approx(0.5)


def test_vanished_live_limit_order_is_cancelled_without_position(
    monkeypatch, isolated_stores, mock_hyperliquid_client
):
    class FakeExchange:
        def update_leverage(self, leverage, symbol, is_cross):
            return {"status": "ok"}

        def order(self, *args, **kwargs):
            return {
                "status": "ok",
                "response": {"data": {"statuses": [{"resting": {"oid": 78}}]}},
            }

    engine = _execution_engine_with_signal(_signal("sig-vanished"), mock_hyperliquid_client)
    monkeypatch.setattr(engine, "_require_live_gates", lambda wallet_id: None)
    monkeypatch.setattr(
        execution_engine_module,
        "_live_exchange",
        lambda wallet, key: FakeExchange(),
    )
    engine.wallet_store.decrypt_private_key = lambda wallet_id, password: "private"
    result = engine.execute(
        "sig-vanished",
        "wallet-live",
        mode="live",
        master_password="password",
        order_type="limit",
        limit_price=99.0,
    )
    mock_hyperliquid_client.open_orders = []
    mock_hyperliquid_client.fills = []

    engine.refresh_positions()

    order = ExecutionStore().get_order(result["order"]["id"])
    assert order is not None
    assert order["status"] == "cancelled"
    assert ExecutionStore().list_open_positions() == []


def test_paper_limit_expiry_marks_order_expired(
    isolated_stores, mock_hyperliquid_client
):
    engine = _execution_engine_with_signal(_signal("sig-expiry"), mock_hyperliquid_client)
    result = engine.execute(
        "sig-expiry",
        "wallet-paper",
        order_type="limit",
        limit_price=99.0,
        expire_minutes=5,
    )
    order = ExecutionStore().get_order(result["order"]["id"])
    assert order is not None
    order["expiresAt"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    ExecutionStore().update_order(order)

    engine.refresh_positions()

    assert ExecutionStore().get_order(order["id"])["status"] == "expired"


def test_pending_exposure_causes_guardrail_rejection(
    isolated_stores, mock_hyperliquid_client
):
    store = ExecutionStore()
    store.create_order(
        {
            **_signal("pending-source"),
            "walletId": "wallet-risk",
            "side": "Buy",
            "price": 99.0,
            "notional": 4900.0,
            "fees": 0.0,
            "type": "Limit",
            "mode": "paper",
            "status": "resting",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "limitPrice": 99.0,
            "filledSize": 0.0,
        }
    )
    from backend.services.portfolio_engine import PortfolioEngine

    with pytest.raises(ValueError, match="pending orders"):
        PortfolioEngine().can_open_position(
            "wallet-risk",
            "BTC",
            200.0,
            2,
            {"maxTotalExposure": 5000.0},
        )


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
    assert [call[0][3] for call in calls] == pytest.approx([98.0 * 0.99, 104.0 * 0.99])


def test_live_protection_uses_worse_closing_bound_for_short(
    isolated_stores, mock_hyperliquid_client
):
    calls = []

    class FakeExchange:
        def order(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {
                "status": "ok",
                "response": {"data": {"statuses": [{"resting": {"oid": 20 + len(calls)}}]}},
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
        "id": "pos-short",
        "walletId": "wallet-short",
        "symbol": "BTC",
        "side": "Sell",
        "size": 1.5,
        "stopPrice": 102.0,
        "takeProfitPrice": 96.0,
        "trailingUnsupported": False,
    }

    engine._place_live_protection(position, FakeExchange())

    assert all(call[0][1] is True for call in calls)
    assert [call[0][3] for call in calls] == pytest.approx([102.0 * 1.01, 96.0 * 1.01])


def test_live_protection_missing_trigger_distinguishes_closed_exchange_position(
    isolated_stores, mock_hyperliquid_client
):
    class FakeStore:
        def __init__(self):
            self.updated = []

        def update_position(self, position):
            self.updated.append(position.copy())
            return position

    alerts = []
    engine = ExecutionEngine()
    engine.store = FakeStore()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    engine.alert_engine = SimpleNamespace(
        protective_unprotected=lambda *args: alerts.append(args),
    )
    position = {
        "id": "pos-monitor",
        "walletId": "wallet-monitor",
        "symbol": "BTC",
        "protectiveStatus": "armed",
        "exchangeStopOrderId": "101",
        "exchangeTakeProfitOrderId": "102",
    }

    engine._monitor_live_protection(position)

    assert position["protectiveStatus"] == "armed"
    assert alerts == []

    mock_hyperliquid_client.clearinghouse["assetPositions"] = [
        {"position": {"coin": "BTC", "szi": "1.0"}}
    ]
    engine._monitor_live_protection(position)

    assert position["protectiveStatus"] == "unprotected"
    assert alerts


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
        def list_pending_orders(self, wallet_id, mode):
            return []

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
            set_live_enabled=lambda wallet_id, enabled: calls.append("disable"),
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

    assert calls == ["disable", "pos-1", "pos-2"]
    assert [item["status"] for item in result["positions"]] == ["error", "closed"]
    assert result["liveEnabled"] is False


def test_kill_switch_settles_local_paper_limit_orders(
    isolated_stores, mock_hyperliquid_client
):
    store = ExecutionStore()
    store.create_order(
        {
            "id": "ord-kill-paper",
            "walletId": "wallet-kill",
            "symbol": "BTC",
            "side": "Buy",
            "size": 1.0,
            "price": 99.0,
            "notional": 99.0,
            "leverage": 2,
            "fees": 0.0,
            "type": "Limit",
            "mode": "paper",
            "status": "resting",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "limitPrice": 99.0,
        }
    )
    calls = []
    engine = ExecutionEngine()
    engine.wallet_store = SimpleNamespace(
        get_wallet=lambda wallet_id: SimpleNamespace(address="0xabc"),
    )
    engine.portfolio_engine = SimpleNamespace(
        portfolio_store=SimpleNamespace(
            set_live_enabled=lambda wallet_id, enabled: calls.append("disable"),
        ),
    )
    engine.alert_engine = SimpleNamespace(kill_switch=lambda *args: None)

    result = engine.kill_switch("wallet-kill", "paper")

    assert calls == ["disable"]
    assert result["orders"][0]["status"] == "cancelled"
    assert store.get_order("ord-kill-paper")["status"] == "cancelled"
