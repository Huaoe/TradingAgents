"""Tests for the execution store."""

from __future__ import annotations

from backend.services.execution_store import ExecutionStore


def _make_order(wallet_id: str = "wallet-1"):
    return {
        "id": "ord-test01",
        "signalId": "sig-test01",
        "walletId": wallet_id,
        "symbol": "BTC",
        "side": "Buy",
        "size": 0.1,
        "price": 100.0,
        "notional": 10.0,
        "leverage": 3,
        "fees": 0.01,
        "mode": "paper",
        "status": "filled",
        "timestamp": "2024-01-01T00:00:00+00:00",
    }


def _make_position(wallet_id: str = "wallet-1"):
    return {
        "id": "pos-test01",
        "orderId": "ord-test01",
        "walletId": wallet_id,
        "symbol": "BTC",
        "side": "Buy",
        "entryPrice": 100.0,
        "markPrice": 101.0,
        "size": 0.1,
        "notional": 10.0,
        "leverage": 3,
        "pnl": 0.1,
        "pnlPct": 1.0,
        "margin": 3.33,
        "status": "open",
        "openedAt": "2024-01-01T00:00:00+00:00",
    }


def test_create_and_fetch_order():
    store = ExecutionStore()
    order = _make_order()
    store.create_order(order)

    fetched = store.get_order(order["id"])
    assert fetched is not None
    assert fetched["id"] == order["id"]
    assert fetched["symbol"] == "BTC"
    assert fetched["type"] == "Market"  # capitalized default

    orders = store.list_orders()
    assert any(o["id"] == order["id"] for o in orders)


def test_create_and_fetch_position():
    store = ExecutionStore()
    position = _make_position()
    store.create_position(position)

    fetched = store.get_position(position["id"])
    assert fetched is not None
    assert fetched["id"] == position["id"]
    assert fetched["status"] == "open"

    positions = store.list_positions()
    assert any(p["id"] == position["id"] for p in positions)

    open_positions = store.list_open_positions()
    assert any(p["id"] == position["id"] for p in open_positions)


def test_list_positions_filters_by_wallet():
    store = ExecutionStore()
    store.create_position(_make_position("wallet-a"))
    store.create_position({**_make_position("wallet-b"), "id": "pos-test02", "orderId": "ord-test02"})

    a_positions = store.list_positions("wallet-a")
    assert all(p["walletId"] == "wallet-a" for p in a_positions)
    assert len(a_positions) == 1

    b_positions = store.list_open_positions("wallet-b")
    assert all(p["walletId"] == "wallet-b" for p in b_positions)
    assert len(b_positions) == 1
