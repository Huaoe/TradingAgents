"""Persistent store for generated signals."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signals.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            size REAL NOT NULL,
            entry REAL NOT NULL,
            stop REAL NOT NULL,
            target REAL NOT NULL,
            leverage INTEGER NOT NULL,
            reasoning TEXT NOT NULL,
            agents TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            meta TEXT
        )
        """
    )
    conn.commit()


def _row_to_signal(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "action": row["action"],
        "confidence": row["confidence"],
        "size": row["size"],
        "entry": row["entry"],
        "stop": row["stop"],
        "target": row["target"],
        "leverage": row["leverage"],
        "reasoning": row["reasoning"],
        "agents": row["agents"].split(","),
        "timestamp": row["timestamp"],
        "status": row["status"],
        "meta": json.loads(row["meta"]) if row["meta"] else None,
    }


class SignalStore:
    """Singleton SQLite-backed signal store."""

    _instance: SignalStore | None = None

    def __new__(cls) -> SignalStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            conn = _get_connection()
            _init_table(conn)
            conn.close()
        return cls._instance

    def list_signals(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [_row_to_signal(r) for r in rows]

    def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return _row_to_signal(row)

    def store_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO signals (id, symbol, action, confidence, size, entry, stop, target,
                leverage, reasoning, agents, timestamp, status, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status
            """,
            (
                signal["id"],
                signal["symbol"],
                signal["action"],
                signal["confidence"],
                signal["size"],
                signal["entry"],
                signal["stop"],
                signal["target"],
                signal["leverage"],
                signal["reasoning"],
                ",".join(signal.get("agents", [])),
                signal["timestamp"],
                signal.get("status", "pending"),
                json.dumps(signal.get("meta")),
            ),
        )
        conn.commit()
        conn.close()
        return signal

    def update_status(self, signal_id: str, status: str) -> bool:
        conn = _get_connection()
        cursor = conn.execute(
            "UPDATE signals SET status = ? WHERE id = ?",
            (status, signal_id),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def delete_signal(self, signal_id: str) -> bool:
        conn = _get_connection()
        cursor = conn.execute("DELETE FROM signals WHERE id = ?", (signal_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0


def signal_store() -> SignalStore:
    return SignalStore()
