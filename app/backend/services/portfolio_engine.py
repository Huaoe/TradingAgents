"""Portfolio summary, wallet balance tracking, and risk guardrails."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.services.execution_store import ExecutionStore

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "portfolio.db")
DEFAULT_PAPER_BALANCE = 10_000.0


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_balance (
            wallet_id TEXT PRIMARY KEY,
            paper_balance REAL NOT NULL DEFAULT 10000.0,
            live_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


class PortfolioStore:
    """Singleton store for per-wallet paper balance and live-trading flag."""

    _instance: PortfolioStore | None = None

    def __new__(cls) -> PortfolioStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            conn = _get_connection()
            _init_tables(conn)
            conn.close()
        return cls._instance

    def _ensure_wallet(self, wallet_id: str) -> None:
        conn = _get_connection()
        row = conn.execute(
            "SELECT 1 FROM wallet_balance WHERE wallet_id = ?", (wallet_id,)
        ).fetchone()
        if not row:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO wallet_balance (wallet_id, paper_balance, live_enabled, updated_at) VALUES (?, ?, 0, ?)",
                (wallet_id, DEFAULT_PAPER_BALANCE, now),
            )
            conn.commit()
        conn.close()

    def get_balance(self, wallet_id: str) -> float:
        self._ensure_wallet(wallet_id)
        conn = _get_connection()
        row = conn.execute(
            "SELECT paper_balance FROM wallet_balance WHERE wallet_id = ?", (wallet_id,)
        ).fetchone()
        conn.close()
        return float(row["paper_balance"]) if row else DEFAULT_PAPER_BALANCE

    def set_balance(self, wallet_id: str, balance: float) -> None:
        self._ensure_wallet(wallet_id)
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_connection()
        conn.execute(
            "UPDATE wallet_balance SET paper_balance = ?, updated_at = ? WHERE wallet_id = ?",
            (balance, now, wallet_id),
        )
        conn.commit()
        conn.close()

    def is_live_enabled(self, wallet_id: str) -> bool:
        self._ensure_wallet(wallet_id)
        conn = _get_connection()
        row = conn.execute(
            "SELECT live_enabled FROM wallet_balance WHERE wallet_id = ?", (wallet_id,)
        ).fetchone()
        conn.close()
        return bool(row["live_enabled"]) if row else False

    def set_live_enabled(self, wallet_id: str, enabled: bool) -> None:
        self._ensure_wallet(wallet_id)
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_connection()
        conn.execute(
            "UPDATE wallet_balance SET live_enabled = ?, updated_at = ? WHERE wallet_id = ?",
            (int(enabled), now, wallet_id),
        )
        conn.commit()
        conn.close()


def portfolio_store() -> PortfolioStore:
    return PortfolioStore()


class PortfolioEngine:
    """Compute portfolio summary and enforce basic risk guardrails."""

    def __init__(self) -> None:
        self.execution_store = ExecutionStore()
        self.portfolio_store = PortfolioStore()

    def summary(self, wallet_id: str | None = None) -> dict[str, Any]:
        positions = self.execution_store.list_positions(wallet_id)
        orders = self.execution_store.list_orders(wallet_id)
        balance = (
            self.portfolio_store.get_balance(wallet_id) if wallet_id else DEFAULT_PAPER_BALANCE
        )

        open_positions = [p for p in positions if p["status"] == "open"]
        margin_used = sum(p["margin"] for p in open_positions)
        unrealized_pnl = sum(p["pnl"] for p in open_positions)
        total_notional = sum(p["notional"] for p in open_positions)

        # Daily realized PnL from orders closed today.
        today = datetime.now(timezone.utc).date().isoformat()
        daily_pnl = 0.0
        for order in orders:
            if order["status"] == "closed" and order["timestamp"].startswith(today):
                meta = order.get("meta") or {}
                daily_pnl += float(meta.get("netPnl") or 0)

        available = max(0.0, balance - margin_used)
        total_value = balance + unrealized_pnl

        # Compute concentration.
        exposure_by_symbol: dict[str, float] = {}
        for p in open_positions:
            exposure_by_symbol[p["symbol"]] = (
                exposure_by_symbol.get(p["symbol"], 0.0) + p["notional"]
            )
        max_symbol = max(exposure_by_symbol, key=exposure_by_symbol.get, default="")
        max_exposure = exposure_by_symbol.get(max_symbol, 0.0)

        return {
            "walletId": wallet_id,
            "mode": "paper"
            if wallet_id and not self.portfolio_store.is_live_enabled(wallet_id)
            else "live",
            "balance": round(balance, 2),
            "available": round(available, 2),
            "marginUsed": round(margin_used, 2),
            "unrealizedPnl": round(unrealized_pnl, 4),
            "dailyPnl": round(daily_pnl, 4),
            "totalValue": round(total_value, 2),
            "totalNotional": round(total_notional, 2),
            "openPositions": len(open_positions),
            "maxExposureSymbol": max_symbol,
            "maxExposureNotional": round(max_exposure, 2),
            "maxLeverage": max((p["leverage"] for p in open_positions), default=0),
        }

    def can_open_position(
        self,
        wallet_id: str,
        symbol: str,
        notional: float,
        leverage: int,
        risk_config: dict[str, Any] | None = None,
    ) -> None:
        """Raise ValueError if a proposed trade violates risk guardrails."""
        cfg = risk_config or {}
        balance = self.portfolio_store.get_balance(wallet_id)
        positions = self.execution_store.list_positions(wallet_id)
        open_positions = [p for p in positions if p["status"] == "open"]

        max_total_exposure = float(cfg.get("maxTotalExposure", balance * 0.5))
        max_position_size = float(cfg.get("maxPositionSize", balance * 0.2))
        max_positions = int(cfg.get("maxOpenPositions", 5))
        daily_loss_limit = float(cfg.get("dailyLossLimit", balance * 0.05))
        max_leverage = int(cfg.get("maxLeverage", 20))

        total_notional = sum(p["notional"] for p in open_positions) + notional
        symbol_exposure = (
            sum(p["notional"] for p in open_positions if p["symbol"] == symbol) + notional
        )

        if notional > max_position_size:
            raise ValueError(
                f"Position size ${notional:.2f} exceeds max position size ${max_position_size:.2f}"
            )
        if total_notional > max_total_exposure:
            raise ValueError(
                f"Total exposure ${total_notional:.2f} exceeds limit ${max_total_exposure:.2f}"
            )
        if symbol_exposure > max_total_exposure * 0.5:
            raise ValueError(
                f"{symbol} concentration ${symbol_exposure:.2f} exceeds 50% of total exposure limit"
            )
        if len(open_positions) >= max_positions:
            raise ValueError(f"Max open positions ({max_positions}) reached")
        if leverage > max_leverage:
            raise ValueError(f"Leverage {leverage}x exceeds max {max_leverage}x")

        # Daily loss check.
        today = datetime.now(timezone.utc).date().isoformat()
        orders = self.execution_store.list_orders(wallet_id)
        daily_pnl = 0.0
        for order in orders:
            if order["status"] == "closed" and order["timestamp"].startswith(today):
                meta = order.get("meta") or {}
                daily_pnl += float(meta.get("netPnl") or 0)
        if daily_pnl < -daily_loss_limit:
            raise ValueError(
                f"Daily loss limit ${daily_loss_limit:.2f} breached (current ${daily_pnl:.2f}); trading halted"
            )

    def reserve_margin(self, wallet_id: str, margin: float) -> None:
        """Subtract margin from available paper balance."""
        balance = self.portfolio_store.get_balance(wallet_id)
        if margin > balance:
            raise ValueError("Insufficient paper balance")
        # Margin is still part of balance; we do not subtract it from total balance.
        # This method is a placeholder for future balance tracking.

    def release_pnl(self, wallet_id: str, net_pnl: float) -> None:
        """Adjust paper balance by realized PnL."""
        balance = self.portfolio_store.get_balance(wallet_id)
        self.portfolio_store.set_balance(wallet_id, balance + net_pnl)
