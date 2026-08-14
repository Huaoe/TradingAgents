"""SQLite-backed store for paper/live orders and positions."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "execution.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            signal_id TEXT,
            wallet_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            size REAL NOT NULL,
            price REAL NOT NULL,
            notional REAL NOT NULL,
            leverage INTEGER NOT NULL,
            fees REAL NOT NULL,
            type TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            meta TEXT
        );

        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            wallet_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            mark_price REAL NOT NULL,
            size REAL NOT NULL,
            notional REAL NOT NULL,
            leverage INTEGER NOT NULL,
            pnl REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            liquidation_price REAL,
            margin REAL NOT NULL,
            status TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        );
        """
    )
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add missing columns to older stores idempotently."""
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE orders ADD COLUMN type TEXT")
    conn.commit()


def _row_to_order(row: sqlite3.Row) -> dict[str, Any]:
    meta = row["meta"]
    return {
        "id": row["id"],
        "signalId": row["signal_id"],
        "walletId": row["wallet_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "size": row["size"],
        "price": row["price"],
        "notional": row["notional"],
        "leverage": row["leverage"],
        "fees": row["fees"],
        "type": (row["type"] or "market").capitalize(),
        "mode": row["mode"],
        "status": row["status"],
        "timestamp": row["timestamp"],
        "meta": json.loads(meta) if meta else None,
    }


def _row_to_position(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "orderId": row["order_id"],
        "walletId": row["wallet_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "entryPrice": row["entry_price"],
        "markPrice": row["mark_price"],
        "size": row["size"],
        "notional": row["notional"],
        "leverage": row["leverage"],
        "pnl": row["pnl"],
        "pnlPct": row["pnl_pct"],
        "liquidationPrice": row["liquidation_price"],
        "margin": row["margin"],
        "status": row["status"],
        "openedAt": row["opened_at"],
        "closedAt": row["closed_at"],
    }


class ExecutionStore:
    """Singleton store for orders and positions."""

    _instance: ExecutionStore | None = None

    def __new__(cls) -> ExecutionStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            conn = _get_connection()
            _init_tables(conn)
            _migrate(conn)
            conn.close()
        return cls._instance

    def create_order(self, order: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO orders (id, signal_id, wallet_id, symbol, side, size, price, notional,
                leverage, fees, type, mode, status, timestamp, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["id"],
                order.get("signalId"),
                order["walletId"],
                order["symbol"],
                order["side"],
                order["size"],
                order["price"],
                order["notional"],
                order["leverage"],
                order["fees"],
                order.get("type", "market"),
                order["mode"],
                order["status"],
                order["timestamp"],
                json.dumps(order.get("meta")),
            ),
        )
        conn.commit()
        conn.close()
        return order

    def create_position(self, position: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO positions (id, order_id, wallet_id, symbol, side, entry_price, mark_price,
                size, notional, leverage, pnl, pnl_pct, liquidation_price, margin, status, opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position["id"],
                position["orderId"],
                position["walletId"],
                position["symbol"],
                position["side"],
                position["entryPrice"],
                position["markPrice"],
                position["size"],
                position["notional"],
                position["leverage"],
                position["pnl"],
                position["pnlPct"],
                position.get("liquidationPrice"),
                position["margin"],
                position["status"],
                position["openedAt"],
                position.get("closedAt"),
            ),
        )
        conn.commit()
        conn.close()
        return position

    def list_orders(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        conn = _get_connection()
        if wallet_id:
            rows = conn.execute(
                "SELECT * FROM orders WHERE wallet_id = ? ORDER BY timestamp DESC",
                (wallet_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders ORDER BY timestamp DESC").fetchall()
        conn.close()
        return [_row_to_order(r) for r in rows]

    def list_positions(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        conn = _get_connection()
        if wallet_id:
            rows = conn.execute(
                "SELECT * FROM positions WHERE wallet_id = ? ORDER BY opened_at DESC",
                (wallet_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM positions ORDER BY opened_at DESC").fetchall()
        conn.close()
        return [_row_to_position(r) for r in rows]

    def list_open_positions(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        conn = _get_connection()
        if wallet_id:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status = 'open' AND wallet_id = ? ORDER BY opened_at DESC",
                (wallet_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at DESC").fetchall()
        conn.close()
        return [_row_to_position(r) for r in rows]

    def mark_position_price(
        self,
        position_id: str,
        mark_price: float,
        pnl: float,
        pnl_pct: float,
    ) -> None:
        conn = _get_connection()
        conn.execute(
            "UPDATE positions SET mark_price = ?, pnl = ?, pnl_pct = ? WHERE id = ?",
            (mark_price, pnl, pnl_pct, position_id),
        )
        conn.commit()
        conn.close()

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return _row_to_position(row)

    def update_position(self, position: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            """
            UPDATE positions
            SET mark_price = ?, pnl = ?, pnl_pct = ?, liquidation_price = ?, margin = ?, status = ?, closed_at = ?
            WHERE id = ?
            """,
            (
                position["markPrice"],
                position["pnl"],
                position["pnlPct"],
                position.get("liquidationPrice"),
                position["margin"],
                position["status"],
                position.get("closedAt"),
                position["id"],
            ),
        )
        conn.commit()
        conn.close()
        return position

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return _row_to_order(row)

    def update_order(self, order: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            "UPDATE orders SET status = ?, meta = ? WHERE id = ?",
            (order["status"], json.dumps(order.get("meta")), order["id"]),
        )
        conn.commit()
        conn.close()
        return order

    def generate_ids(self) -> tuple[str, str]:
        return f"ord-{uuid.uuid4().hex[:8]}", f"pos-{uuid.uuid4().hex[:8]}"


def execution_store() -> ExecutionStore:
    return ExecutionStore()
