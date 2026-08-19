"""Portfolio summary, wallet balance tracking, and risk guardrails."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.llm_usage_store import LlmUsageStore
from backend.services.wallet_store import WalletStore

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            total_value REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_portfolio_history_wallet ON portfolio_history(wallet_id, timestamp)"
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

    def list_live_wallet_ids(self) -> list[str]:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT wallet_id FROM wallet_balance WHERE live_enabled = 1"
        ).fetchall()
        conn.close()
        return [str(row["wallet_id"]) for row in rows]

    def record_history(self, wallet_id: str, total_value: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_connection()
        conn.execute(
            "INSERT INTO portfolio_history (wallet_id, timestamp, total_value) VALUES (?, ?, ?)",
            (wallet_id, now, total_value),
        )
        conn.commit()
        conn.close()

    def get_history(self, wallet_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = _get_connection()
        if wallet_id:
            rows = conn.execute(
                "SELECT * FROM portfolio_history WHERE wallet_id = ? ORDER BY timestamp DESC LIMIT ?",
                (wallet_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM portfolio_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        points = [
            {
                "timestamp": row["timestamp"],
                "totalValue": float(row["total_value"]),
            }
            for row in reversed(rows)
        ]
        return points


def portfolio_store() -> PortfolioStore:
    return PortfolioStore()


class PortfolioEngine:
    """Compute portfolio summary and enforce basic risk guardrails."""

    def __init__(self) -> None:
        self.execution_store = ExecutionStore()
        self.portfolio_store = PortfolioStore()
        self.wallet_store = WalletStore()
        self.client = HyperliquidClient()

    def summary(self, wallet_id: str | None = None) -> dict[str, Any]:
        mode = "live" if wallet_id and self.portfolio_store.is_live_enabled(wallet_id) else "paper"
        positions = [
            position
            for position in self.execution_store.list_positions(wallet_id)
            if position.get("mode", "paper") == mode
        ]
        orders = [
            order
            for order in self.execution_store.list_orders(wallet_id)
            if order.get("mode", "paper") == mode
        ]
        balance = (
            self.portfolio_store.get_balance(wallet_id) if wallet_id else DEFAULT_PAPER_BALANCE
        )
        balance_source = "paper_store"
        exchange_total_value: float | None = None
        exchange_margin_used: float | None = None
        exchange_available: float | None = None
        exchange_unrealized_pnl: float | None = None
        exchange_total_notional: float | None = None
        if mode == "live" and wallet_id:
            wallet = self.wallet_store.get_wallet(wallet_id)
            if wallet:
                try:
                    state = self.client.get_clearinghouse_state(wallet.address)
                    margin = state.get("marginSummary") or state.get("crossMarginSummary") or {}
                    exchange_total_value = float(margin.get("accountValue") or 0.0)
                    exchange_margin_used = float(margin.get("totalMarginUsed") or 0.0)
                    withdrawable = margin.get("withdrawable", state.get("withdrawable"))
                    exchange_available = (
                        float(withdrawable)
                        if withdrawable is not None
                        else max(0.0, exchange_total_value - exchange_margin_used)
                    )
                    exchange_asset_positions = state.get("assetPositions", [])
                    exchange_unrealized_pnl = sum(
                        float(item.get("position", {}).get("unrealizedPnl") or 0.0)
                        for item in exchange_asset_positions
                    )
                    exchange_total_notional = sum(
                        abs(float(item.get("position", {}).get("positionValue") or 0.0))
                        for item in exchange_asset_positions
                    )
                    balance = exchange_total_value
                    balance_source = "exchange"
                except Exception:  # noqa: BLE001
                    pass

        open_positions = [p for p in positions if p["status"] == "open"]
        margin_used = sum(p["margin"] for p in open_positions)
        unrealized_pnl = sum(p["pnl"] for p in open_positions)
        total_notional = sum(p["notional"] for p in open_positions)
        if balance_source == "exchange":
            unrealized_pnl = exchange_unrealized_pnl or 0.0
            total_notional = exchange_total_notional or 0.0

        # Daily realized PnL from orders closed today.
        today = datetime.now(timezone.utc).date().isoformat()
        daily_pnl = 0.0
        for order in orders:
            if order["status"] == "closed" and order["timestamp"].startswith(today):
                meta = order.get("meta") or {}
                daily_pnl += float(meta.get("netPnl") or 0)

        available = (
            exchange_available
            if balance_source == "exchange" and exchange_available is not None
            else max(0.0, balance - margin_used)
        )
        if balance_source == "exchange" and exchange_margin_used is not None:
            margin_used = exchange_margin_used
        total_value = (
            exchange_total_value
            if balance_source == "exchange" and exchange_total_value is not None
            else balance + unrealized_pnl
        )

        # Compute concentration.
        exposure_by_symbol: dict[str, float] = {}
        for p in open_positions:
            exposure_by_symbol[p["symbol"]] = (
                exposure_by_symbol.get(p["symbol"], 0.0) + p["notional"]
            )
        max_symbol = max(exposure_by_symbol, key=exposure_by_symbol.get, default="")
        max_exposure = exposure_by_symbol.get(max_symbol, 0.0)

        usage = LlmUsageStore().get_total()

        return {
            "walletId": wallet_id,
            "mode": mode,
            "balanceSource": balance_source,
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
            "llmSpend": round(usage["spend"], 4),
            "llmTokensIn": usage["tokens_in"],
            "llmTokensOut": usage["tokens_out"],
            "llmCalls": usage["llm_calls"],
        }

    def record_history(self) -> None:
        from backend.services.wallet_store import WalletStore

        wallets = WalletStore().list_wallets()
        for wallet in wallets:
            summary = self.summary(wallet.id)
            self.portfolio_store.record_history(wallet.id, summary["totalValue"])

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
        mode = "live" if self.portfolio_store.is_live_enabled(wallet_id) else "paper"
        balance = self._account_balance(wallet_id, mode)
        positions = [
            position
            for position in self.execution_store.list_positions(wallet_id)
            if position.get("mode", "paper") == mode
        ]
        open_positions = [p for p in positions if p["status"] == "open"]
        pending_orders = self.execution_store.list_pending_orders(wallet_id, mode)
        pending_notional = sum(
            max(0.0, float(order["size"]) - float(order.get("filledSize") or 0.0))
            * float(order.get("limitPrice") or order["price"])
            for order in pending_orders
        )
        pending_symbol_notional = sum(
            max(0.0, float(order["size"]) - float(order.get("filledSize") or 0.0))
            * float(order.get("limitPrice") or order["price"])
            for order in pending_orders
            if order["symbol"] == symbol
        )

        max_total_exposure = float(cfg.get("maxTotalExposure", balance * 0.5))
        max_position_size = float(cfg.get("maxPositionSize", balance * 0.2))
        max_positions = int(cfg.get("maxOpenPositions", 5))
        daily_loss_limit = float(cfg.get("dailyLossLimit", balance * 0.05))
        max_leverage = int(cfg.get("maxLeverage", 20))

        total_notional = sum(p["notional"] for p in open_positions) + pending_notional + notional
        symbol_exposure = (
            sum(p["notional"] for p in open_positions if p["symbol"] == symbol)
            + pending_symbol_notional
            + notional
        )

        if notional > max_position_size:
            raise ValueError(
                f"Position size ${notional:.2f} exceeds max position size ${max_position_size:.2f}"
            )
        if total_notional > max_total_exposure:
            raise ValueError(
                f"Total exposure ${total_notional:.2f} exceeds limit ${max_total_exposure:.2f}"
                + (" because of pending orders" if pending_notional else "")
            )
        if symbol_exposure > max_total_exposure * 0.5:
            raise ValueError(
                f"{symbol} concentration ${symbol_exposure:.2f} exceeds 50% of total exposure limit"
                + (" because of pending orders" if pending_symbol_notional else "")
            )
        if len(open_positions) + len(pending_orders) >= max_positions:
            raise ValueError(
                f"Max open positions ({max_positions}) reached"
                + (" because of pending orders" if pending_orders else "")
            )
        if leverage > max_leverage:
            raise ValueError(f"Leverage {leverage}x exceeds max {max_leverage}x")

        # Daily loss check.
        today = datetime.now(timezone.utc).date().isoformat()
        orders = [
            order
            for order in self.execution_store.list_orders(wallet_id)
            if order.get("mode", "paper") == mode
        ]
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

    def _account_balance(self, wallet_id: str, mode: str) -> float:
        if mode == "live":
            wallet = self.wallet_store.get_wallet(wallet_id)
            if wallet:
                try:
                    state = self.client.get_clearinghouse_state(wallet.address)
                    margin = state.get("marginSummary") or state.get("crossMarginSummary") or {}
                    return float(margin.get("accountValue") or 0.0)
                except Exception:  # noqa: BLE001
                    pass
        return self.portfolio_store.get_balance(wallet_id)

    def release_pnl(self, wallet_id: str, net_pnl: float, mode: str = "paper") -> None:
        """Adjust paper balance by realized PnL; exchange balances are read-only here."""
        if mode == "live":
            return
        balance = self.portfolio_store.get_balance(wallet_id)
        self.portfolio_store.set_balance(wallet_id, balance + net_pnl)
