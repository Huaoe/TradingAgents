"""Alert and trade-journal storage."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            wallet_id TEXT,
            related_id TEXT,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trade_journal (
            id TEXT PRIMARY KEY,
            wallet_id TEXT,
            position_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            size REAL NOT NULL,
            leverage INTEGER NOT NULL,
            gross_pnl REAL NOT NULL,
            fees REAL NOT NULL,
            net_pnl REAL NOT NULL,
            reasoning TEXT,
            reflection TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _row_to_alert(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "walletId": row["wallet_id"],
        "relatedId": row["related_id"],
        "type": row["type"],
        "severity": row["severity"],
        "message": row["message"],
        "read": bool(row["read"]),
        "timestamp": row["timestamp"],
    }


def _row_to_journal(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "walletId": row["wallet_id"],
        "positionId": row["position_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "entryPrice": row["entry_price"],
        "exitPrice": row["exit_price"],
        "size": row["size"],
        "leverage": row["leverage"],
        "grossPnl": row["gross_pnl"],
        "fees": row["fees"],
        "netPnl": row["net_pnl"],
        "reasoning": row["reasoning"],
        "reflection": row["reflection"],
        "openedAt": row["opened_at"],
        "closedAt": row["closed_at"],
    }


class AlertStore:
    """Singleton store for alerts and trade-journal entries."""

    _instance: AlertStore | None = None

    def __new__(cls) -> AlertStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            conn = _get_connection()
            _init_tables(conn)
            conn.close()
        return cls._instance

    def create_alert(
        self,
        type_: str,
        severity: str,
        message: str,
        wallet_id: str | None = None,
        related_id: str | None = None,
    ) -> dict[str, Any]:
        conn = _get_connection()
        alert_id = f"alrt-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO alerts (id, wallet_id, related_id, type, severity, message, read, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (alert_id, wallet_id, related_id, type_, severity, message, now),
        )
        conn.commit()
        conn.close()
        return {
            "id": alert_id,
            "walletId": wallet_id,
            "relatedId": related_id,
            "type": type_,
            "severity": severity,
            "message": message,
            "read": False,
            "timestamp": now,
        }

    def list_alerts(
        self,
        wallet_id: str | None = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = _get_connection()
        params: list[Any] = []
        query = "SELECT * FROM alerts"
        conditions: list[str] = []
        if wallet_id:
            conditions.append("wallet_id = ?")
            params.append(wallet_id)
        if unread_only:
            conditions.append("read = 0")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [_row_to_alert(r) for r in rows]

    def mark_read(self, alert_id: str) -> bool:
        conn = _get_connection()
        cursor = conn.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def mark_all_read(self, wallet_id: str | None = None) -> bool:
        conn = _get_connection()
        if wallet_id:
            cursor = conn.execute("UPDATE alerts SET read = 1 WHERE wallet_id = ?", (wallet_id,))
        else:
            cursor = conn.execute("UPDATE alerts SET read = 1")
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def unread_count(self, wallet_id: str | None = None) -> int:
        conn = _get_connection()
        if wallet_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE read = 0 AND wallet_id = ?",
                (wallet_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM alerts WHERE read = 0").fetchone()
        conn.close()
        return int(row[0]) if row else 0

    def add_journal_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        entry_id = f"jrnl-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """
            INSERT INTO trade_journal (id, wallet_id, position_id, symbol, side, entry_price, exit_price,
                size, leverage, gross_pnl, fees, net_pnl, reasoning, reflection, opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                entry.get("walletId"),
                entry.get("positionId"),
                entry["symbol"],
                entry["side"],
                entry["entryPrice"],
                entry["exitPrice"],
                entry["size"],
                entry["leverage"],
                entry["grossPnl"],
                entry["fees"],
                entry["netPnl"],
                entry.get("reasoning"),
                entry.get("reflection"),
                entry["openedAt"],
                entry["closedAt"],
            ),
        )
        conn.commit()
        conn.close()
        return {**entry, "id": entry_id}

    def list_journal(self, wallet_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = _get_connection()
        if wallet_id:
            rows = conn.execute(
                "SELECT * FROM trade_journal WHERE wallet_id = ? ORDER BY closed_at DESC LIMIT ?",
                (wallet_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trade_journal ORDER BY closed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        return [_row_to_journal(r) for r in rows]


def alert_store() -> AlertStore:
    return AlertStore()
