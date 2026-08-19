"""Alerting and reflection utilities for the trading agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services.alert_store import AlertStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reflect(reasoning: str | None, net_pnl: float) -> str:
    """Generate a deterministic post-trade reflection based on the outcome."""
    if net_pnl > 0:
        return f"Trade was profitable (${net_pnl:.4f}). Review whether the setup matched the reasoning: {reasoning or 'No reasoning provided.'}"
    if net_pnl < 0:
        return f"Trade lost ${abs(net_pnl):.4f}. Compare execution against the original signal reasoning and check stop/target placement."
    return "Trade closed flat. Review fees and slippage assumptions."


class AlertEngine:
    """Create alerts and journal entries for signals, positions, and risk events."""

    def __init__(self) -> None:
        self.store = AlertStore()

    def signal_generated(self, signal: dict[str, Any]) -> dict[str, Any]:
        return self.store.create_alert(
            type_="signal",
            severity="info",
            message=f"Generated {signal['action']} signal for {signal['symbol']} with {signal['confidence']}% confidence.",
            wallet_id=None,
            related_id=signal["id"],
        )

    def signal_accepted(self, signal: dict[str, Any], wallet_id: str) -> dict[str, Any]:
        return self.store.create_alert(
            type_="signal",
            severity="info",
            message=f"Signal {signal['symbol']} accepted for execution.",
            wallet_id=wallet_id,
            related_id=signal["id"],
        )

    def position_opened(self, position: dict[str, Any], wallet_id: str) -> dict[str, Any]:
        side = position.get("side", "LONG")
        leverage = position.get("leverage", 1)
        return self.store.create_alert(
            type_="position",
            severity="success",
            message=f"Opened {side} {position['symbol']} position at {position.get('entryPrice', 0)} with {leverage}x leverage.",
            wallet_id=wallet_id,
            related_id=position["id"],
        )

    def position_closed(
        self,
        position: dict[str, Any],
        net_pnl: float,
        wallet_id: str,
    ) -> dict[str, Any]:
        side = position.get("side", "LONG")
        severity = "success" if net_pnl >= 0 else "warning"
        msg = f"Closed {side} {position['symbol']} position. Net PnL: ${net_pnl:.4f}."
        return self.store.create_alert(
            type_="position",
            severity=severity,
            message=msg,
            wallet_id=wallet_id,
            related_id=position["id"],
        )

    def risk_violation(self, message: str, wallet_id: str | None = None) -> dict[str, Any]:
        return self.store.create_alert(
            type_="risk",
            severity="error",
            message=message,
            wallet_id=wallet_id,
        )

    def execution_divergence(
        self,
        message: str,
        wallet_id: str,
        related_id: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="execution_divergence",
            severity="error",
            message=message,
            wallet_id=wallet_id,
            related_id=related_id,
        )

    def reconciliation_divergence(
        self,
        message: str,
        severity: str,
        wallet_id: str,
        related_id: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="reconciliation",
            severity=severity,
            message=message,
            wallet_id=wallet_id,
            related_id=related_id,
        )

    def protective_unprotected(
        self,
        message: str,
        wallet_id: str,
        related_id: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="protective_exit",
            severity="error",
            message=message,
            wallet_id=wallet_id,
            related_id=related_id,
        )

    def protective_unsupported(
        self,
        position: dict[str, Any],
        wallet_id: str,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="protective_exit",
            severity="warning",
            message=(
                f"Live trailing stop is unsupported for {position['symbol']}; "
                "Hyperliquid has no native trailing trigger."
            ),
            wallet_id=wallet_id,
            related_id=position["id"],
        )

    def protective_triggered(
        self,
        position: dict[str, Any],
        reason: str,
        trigger_price: float,
        wallet_id: str,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="protective_exit",
            severity="warning",
            message=(
                f"{reason} triggered for {position['symbol']} at theoretical "
                f"price {trigger_price:.8f}."
            ),
            wallet_id=wallet_id,
            related_id=position["id"],
        )

    def kill_switch(
        self,
        wallet_id: str,
        mode: str,
    ) -> dict[str, Any]:
        return self.store.create_alert(
            type_="kill_switch",
            severity="error",
            message=f"Kill switch invoked for {mode} mode.",
            wallet_id=wallet_id,
        )

    def journal_closed_trade(
        self,
        position: dict[str, Any],
        order: dict[str, Any] | None,
        net_pnl: float,
        gross_pnl: float,
        fees: float,
        wallet_id: str,
    ) -> dict[str, Any]:
        reasoning: str | None = None
        if order and order.get("meta"):
            signal = order["meta"].get("signal") or {}
            reasoning = signal.get("reasoning")
        reflection = _reflect(reasoning, net_pnl)
        entry = {
            "walletId": wallet_id,
            "positionId": position["id"],
            "symbol": position["symbol"],
            "side": position.get("side", "LONG"),
            "entryPrice": position["entryPrice"],
            "exitPrice": position.get("markPrice", position["entryPrice"]),
            "size": position["size"],
            "leverage": position["leverage"],
            "grossPnl": round(gross_pnl, 4),
            "fees": round(fees, 4),
            "netPnl": round(net_pnl, 4),
            "reasoning": reasoning,
            "reflection": reflection,
            "openedAt": position["openedAt"],
            "closedAt": _now(),
        }
        return self.store.add_journal_entry(entry)

    def list_alerts(
        self,
        wallet_id: str | None = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.store.list_alerts(wallet_id, unread_only, limit)

    def mark_read(self, alert_id: str) -> bool:
        return self.store.mark_read(alert_id)

    def unread_count(self, wallet_id: str | None = None) -> int:
        return self.store.unread_count(wallet_id)

    def list_journal(self, wallet_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_journal(wallet_id, limit)
