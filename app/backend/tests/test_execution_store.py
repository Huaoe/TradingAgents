"""Tests for the execution store."""

from __future__ import annotations

import sqlite3

import backend.services.execution_store as execution_store_module
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


def test_position_mode_migrates_and_backfills_from_originating_order():
    conn = sqlite3.connect(execution_store_module.DB_PATH)
    conn.executescript(
        """
        CREATE TABLE orders (
            id TEXT PRIMARY KEY, signal_id TEXT, wallet_id TEXT, symbol TEXT, side TEXT,
            size REAL, price REAL, notional REAL, leverage INTEGER, fees REAL,
            type TEXT, mode TEXT, status TEXT, timestamp TEXT, meta TEXT
        );
        CREATE TABLE positions (
            id TEXT PRIMARY KEY, order_id TEXT, wallet_id TEXT, symbol TEXT, side TEXT,
            entry_price REAL, mark_price REAL, size REAL, notional REAL, leverage INTEGER,
            pnl REAL, pnl_pct REAL, liquidation_price REAL, margin REAL, status TEXT,
            opened_at TEXT, closed_at TEXT
        );
        INSERT INTO orders VALUES (
            'ord-live', NULL, 'wallet-1', 'BTC', 'Buy', 1, 100, 100, 2, 0.1,
            'Market', 'live', 'filled', '2024-01-01T00:00:00+00:00', NULL
        );
        INSERT INTO positions VALUES (
            'pos-live', 'ord-live', 'wallet-1', 'BTC', 'Buy', 100, 100, 1, 100, 2,
            0, 0, NULL, 50, 'open', '2024-01-01T00:00:00+00:00', NULL
        );
        """
    )
    conn.commit()
    conn.close()

    position = ExecutionStore().get_position("pos-live")
    order = ExecutionStore().get_order("ord-live")

    assert position is not None
    assert order is not None
    assert order["filledSize"] == 0.0
    assert order["limitPrice"] is None
    assert order["exchangeOrderId"] is None
    assert position["mode"] == "live"
    assert position["protectiveStatus"] == "disabled"
    assert position["stopPrice"] is None
