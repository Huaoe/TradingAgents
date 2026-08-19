"""SQLite-backed store for paper/live orders and positions."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
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
            meta TEXT,
            limit_price REAL,
            tif TEXT,
            filled_size REAL NOT NULL DEFAULT 0,
            expires_at TEXT,
            exchange_order_id TEXT,
            updated_at TEXT
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
            mode TEXT NOT NULL DEFAULT 'paper',
            stop_price REAL,
            take_profit_price REAL,
            trailing_stop_pct REAL,
            trailing_watermark REAL,
            exit_reason TEXT,
            protective_status TEXT NOT NULL DEFAULT 'disabled',
            exchange_stop_order_id TEXT,
            exchange_take_profit_order_id TEXT,
            trailing_unsupported INTEGER NOT NULL DEFAULT 0,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS reconciliations (
            id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            divergences TEXT NOT NULL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reconciliations_wallet
            ON reconciliations(wallet_id, timestamp);
        """
    )
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add missing columns to older stores idempotently."""
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE orders ADD COLUMN type TEXT")
    for definition in (
        "limit_price REAL",
        "tif TEXT",
        "filled_size REAL NOT NULL DEFAULT 0",
        "expires_at TEXT",
        "exchange_order_id TEXT",
        "updated_at TEXT",
    ):
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE orders ADD COLUMN {definition}")
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE positions ADD COLUMN mode TEXT NOT NULL DEFAULT 'paper'")
    for definition in (
        "stop_price REAL",
        "take_profit_price REAL",
        "trailing_stop_pct REAL",
        "trailing_watermark REAL",
        "exit_reason TEXT",
        "protective_status TEXT NOT NULL DEFAULT 'disabled'",
        "exchange_stop_order_id TEXT",
        "exchange_take_profit_order_id TEXT",
        "trailing_unsupported INTEGER NOT NULL DEFAULT 0",
    ):
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE positions ADD COLUMN {definition}")
    conn.execute(
        """
        UPDATE positions
        SET mode = COALESCE(
            (SELECT mode FROM orders WHERE orders.id = positions.order_id),
            'paper'
        )
        WHERE EXISTS (SELECT 1 FROM orders WHERE orders.id = positions.order_id)
        """
    )
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
        "limitPrice": row["limit_price"],
        "tif": row["tif"],
        "filledSize": row["filled_size"] or 0.0,
        "expiresAt": row["expires_at"],
        "exchangeOrderId": row["exchange_order_id"],
        "updatedAt": row["updated_at"],
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
        "mode": row["mode"] or "paper",
        "stopPrice": row["stop_price"],
        "takeProfitPrice": row["take_profit_price"],
        "trailingStopPct": row["trailing_stop_pct"],
        "trailingWatermark": row["trailing_watermark"],
        "exitReason": row["exit_reason"],
        "protectiveStatus": row["protective_status"] or "disabled",
        "exchangeStopOrderId": row["exchange_stop_order_id"],
        "exchangeTakeProfitOrderId": row["exchange_take_profit_order_id"],
        "trailingUnsupported": bool(row["trailing_unsupported"]),
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
                leverage, fees, type, mode, status, timestamp, meta, limit_price, tif,
                filled_size, expires_at, exchange_order_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                order.get("limitPrice"),
                order.get("tif"),
                order.get("filledSize", 0.0),
                order.get("expiresAt"),
                order.get("exchangeOrderId"),
                order.get("updatedAt") or order["timestamp"],
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
                size, notional, leverage, pnl, pnl_pct, liquidation_price, margin, status, mode,
                stop_price, take_profit_price, trailing_stop_pct, trailing_watermark, exit_reason,
                protective_status, exchange_stop_order_id, exchange_take_profit_order_id,
                trailing_unsupported, opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                position.get("mode", "paper"),
                position.get("stopPrice"),
                position.get("takeProfitPrice"),
                position.get("trailingStopPct"),
                position.get("trailingWatermark"),
                position.get("exitReason"),
                position.get("protectiveStatus", "disabled"),
                position.get("exchangeStopOrderId"),
                position.get("exchangeTakeProfitOrderId"),
                int(position.get("trailingUnsupported", False)),
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
            SET mark_price = ?, pnl = ?, pnl_pct = ?, liquidation_price = ?, margin = ?, status = ?,
                stop_price = ?, take_profit_price = ?, trailing_stop_pct = ?, trailing_watermark = ?,
                exit_reason = ?, protective_status = ?, exchange_stop_order_id = ?,
                exchange_take_profit_order_id = ?, trailing_unsupported = ?, closed_at = ?
            WHERE id = ?
            """,
            (
                position["markPrice"],
                position["pnl"],
                position["pnlPct"],
                position.get("liquidationPrice"),
                position["margin"],
                position["status"],
                position.get("stopPrice"),
                position.get("takeProfitPrice"),
                position.get("trailingStopPct"),
                position.get("trailingWatermark"),
                position.get("exitReason"),
                position.get("protectiveStatus", "disabled"),
                position.get("exchangeStopOrderId"),
                position.get("exchangeTakeProfitOrderId"),
                int(position.get("trailingUnsupported", False)),
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
        updated_at = order.get("updatedAt") or datetime.now(timezone.utc).isoformat()
        order["updatedAt"] = updated_at
        conn = _get_connection()
        conn.execute(
            """
            UPDATE orders
            SET price = ?, notional = ?, fees = ?, type = ?, status = ?, meta = ?,
                limit_price = ?, tif = ?, filled_size = ?, expires_at = ?,
                exchange_order_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                order["price"],
                order["notional"],
                order["fees"],
                order.get("type", "Market"),
                order["status"],
                json.dumps(order.get("meta")),
                order.get("limitPrice"),
                order.get("tif"),
                order.get("filledSize", 0.0),
                order.get("expiresAt"),
                order.get("exchangeOrderId"),
                updated_at,
                order["id"],
            ),
        )
        conn.commit()
        conn.close()
        return order

    def list_pending_orders(
        self,
        wallet_id: str | None = None,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = _get_connection()
        clauses = ["status IN ('resting', 'partially_filled')"]
        params: list[Any] = []
        if wallet_id:
            clauses.append("wallet_id = ?")
            params.append(wallet_id)
        if mode:
            clauses.append("mode = ?")
            params.append(mode)
        rows = conn.execute(
            f"SELECT * FROM orders WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC",
            params,
        ).fetchall()
        conn.close()
        return [_row_to_order(row) for row in rows]

    def list_resting_orders(
        self,
        wallet_id: str | None = None,
        mode: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_pending_orders(wallet_id, mode)

    def update_order_progress(
        self,
        order_id: str,
        filled_size: float,
        status: str,
        *,
        fees: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        order = self.get_order(order_id)
        if not order:
            return None
        order["filledSize"] = filled_size
        order["status"] = status
        if fees is not None:
            order["fees"] = fees
        if meta is not None:
            order["meta"] = meta
        return self.update_order(order)

    def get_order_by_exchange_id(
        self,
        wallet_id: str,
        exchange_order_id: str,
    ) -> dict[str, Any] | None:
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM orders WHERE wallet_id = ? AND exchange_order_id = ?",
            (wallet_id, exchange_order_id),
        ).fetchone()
        conn.close()
        return _row_to_order(row) if row else None

    def save_reconciliation(self, reconciliation: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO reconciliations
                (id, wallet_id, timestamp, status, divergences, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                reconciliation["id"],
                reconciliation["walletId"],
                reconciliation["timestamp"],
                reconciliation["status"],
                json.dumps(reconciliation.get("divergences", [])),
                reconciliation.get("error"),
            ),
        )
        conn.commit()
        conn.close()
        return reconciliation

    def get_last_reconciliation(self, wallet_id: str) -> dict[str, Any] | None:
        conn = _get_connection()
        row = conn.execute(
            """
            SELECT * FROM reconciliations
            WHERE wallet_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (wallet_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row["id"],
            "walletId": row["wallet_id"],
            "timestamp": row["timestamp"],
            "status": row["status"],
            "divergences": json.loads(row["divergences"]),
            "error": row["error"],
        }

    def generate_ids(self) -> tuple[str, str]:
        return f"ord-{uuid.uuid4().hex[:8]}", f"pos-{uuid.uuid4().hex[:8]}"


def execution_store() -> ExecutionStore:
    return ExecutionStore()
