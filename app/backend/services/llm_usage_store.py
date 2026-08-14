"""Persisted store for cumulative LLM token usage."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, ClassVar

from backend.services.llm_cost import estimate_cost

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "llm_usage.db")
_TABLE = "llm_usage"


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id INTEGER PRIMARY KEY,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            llm_calls INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {_TABLE} (id, tokens_in, tokens_out, llm_calls, updated_at)
        VALUES (1, 0, 0, 0, ?)
        """,
        (now,),
    )
    conn.commit()


class LlmUsageStore:
    """Singleton SQLite store that keeps a running total of LLM usage."""

    _instance: ClassVar[LlmUsageStore | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> LlmUsageStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                conn = _get_connection()
                _init_tables(conn)
                conn.close()
        return cls._instance

    def record(self, tokens_in: int, tokens_out: int, llm_calls: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = _get_connection()
            conn.execute(
                f"""
                UPDATE {_TABLE}
                SET tokens_in = tokens_in + ?,
                    tokens_out = tokens_out + ?,
                    llm_calls = llm_calls + ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (tokens_in, tokens_out, llm_calls, now),
            )
            conn.commit()
            conn.close()

    def get_total(self) -> dict[str, Any]:
        with self._lock:
            conn = _get_connection()
            row = conn.execute(f"SELECT * FROM {_TABLE} WHERE id = 1").fetchone()
            conn.close()
            if not row:
                return {
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "llm_calls": 0,
                    "spend": 0.0,
                }
            tokens_in = int(row["tokens_in"])
            tokens_out = int(row["tokens_out"])
            return {
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "llm_calls": int(row["llm_calls"]),
                "spend": estimate_cost(tokens_in, tokens_out),
            }
