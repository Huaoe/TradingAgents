"""Read-only reconciliation between persisted live positions and Hyperliquid."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.services.alert_engine import AlertEngine
from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.portfolio_engine import PortfolioStore
from backend.services.wallet_store import WalletStore

RELATIVE_SIZE_TOLERANCE = 0.001
ABSOLUTE_SIZE_TOLERANCE = 1e-6
ENTRY_PRICE_TOLERANCE = 0.005


def _exchange_positions(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    positions: dict[str, dict[str, Any]] = {}
    for item in state.get("assetPositions", []):
        position = item.get("position", item)
        size = float(position.get("szi") or 0.0)
        if not size:
            continue
        coin = str(position.get("coin") or "").upper()
        if not coin:
            continue
        positions[coin] = {
            "symbol": coin,
            "signedSize": size,
            "entryPrice": float(position.get("entryPx") or 0.0),
        }
    return positions


def _size_matches(local_size: float, exchange_size: float) -> bool:
    tolerance = max(ABSOLUTE_SIZE_TOLERANCE, abs(exchange_size) * RELATIVE_SIZE_TOLERANCE)
    return abs(local_size - exchange_size) <= tolerance


class ReconciliationService:
    """Compare live positions without ever mutating local execution state."""

    def __init__(
        self,
        client: HyperliquidClient | None = None,
        store: ExecutionStore | None = None,
        wallet_store: WalletStore | None = None,
        portfolio_store: PortfolioStore | None = None,
        alert_engine: AlertEngine | None = None,
    ) -> None:
        self.client = client or HyperliquidClient()
        self.store = store or ExecutionStore()
        self.wallet_store = wallet_store or WalletStore()
        self.portfolio_store = portfolio_store or PortfolioStore()
        self.alert_engine = alert_engine or AlertEngine()

    def reconcile(self, wallet_id: str) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        result: dict[str, Any] = {
            "id": f"rec-{uuid.uuid4().hex[:8]}",
            "walletId": wallet_id,
            "timestamp": timestamp,
            "status": "unavailable",
            "divergences": [],
            "error": None,
        }
        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            result["error"] = f"Wallet {wallet_id} not found"
            self.store.save_reconciliation(result)
            return result
        if not self.portfolio_store.is_live_enabled(wallet_id):
            result["status"] = "not_applicable"
            result["error"] = f"Live trading is not enabled for wallet {wallet_id}"
            self.store.save_reconciliation(result)
            return result

        try:
            state = self.client.get_clearinghouse_state(wallet.address, force=True)
            exchange = _exchange_positions(state)
            local: dict[str, dict[str, Any]] = {}
            for position in self.store.list_open_positions(wallet_id):
                if position.get("mode", "paper") != "live":
                    continue
                symbol = position["symbol"].upper()
                signed_size = (
                    float(position["size"])
                    if position["side"] in {"Buy", "LONG"}
                    else -float(position["size"])
                )
                aggregate = local.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "signedSize": 0.0,
                        "entryNotional": 0.0,
                        "entrySize": 0.0,
                        "positionIds": [],
                    },
                )
                aggregate["signedSize"] += signed_size
                aggregate["entryNotional"] += abs(float(position["size"])) * float(
                    position["entryPrice"]
                )
                aggregate["entrySize"] += abs(float(position["size"]))
                aggregate["positionIds"].append(position["id"])
            for aggregate in local.values():
                aggregate["entryPrice"] = (
                    aggregate["entryNotional"] / aggregate["entrySize"]
                    if aggregate["entrySize"]
                    else 0.0
                )
            divergences = self._compare(local, exchange)
            result["divergences"] = divergences
            result["status"] = "diverged" if divergences else "ok"
            self._alert_on_change(wallet_id, divergences)
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)

        self.store.save_reconciliation(result)
        return result

    def _compare(
        self,
        local: dict[str, dict[str, Any]],
        exchange: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        divergences: list[dict[str, Any]] = []
        for symbol, position in local.items():
            remote = exchange.get(symbol)
            local_size = float(position["signedSize"])
            local_side = "Buy" if local_size > 0 else "Sell" if local_size < 0 else None
            local_ids = position["positionIds"]
            if remote is None:
                if local_side is None:
                    continue
                divergences.append(
                    {
                        "type": "missing_on_exchange",
                        "severity": "error",
                        "symbol": symbol,
                        "localPositionIds": local_ids,
                        "localSize": local_size,
                        "message": f"Local live position {symbol} is missing on the exchange.",
                    }
                )
                continue
            exchange_size = float(remote["signedSize"])
            exchange_side = (
                "Buy" if exchange_size > 0 else "Sell" if exchange_size < 0 else None
            )
            if local_side != exchange_side:
                divergences.append(
                    {
                        "type": "side_mismatch",
                        "severity": "error",
                        "symbol": symbol,
                        "localPositionIds": local_ids,
                        "localSide": local_side,
                        "exchangeSide": exchange_side,
                        "message": f"Local {local_side} position conflicts with exchange {exchange_side}.",
                    }
                )
            if not _size_matches(abs(local_size), abs(exchange_size)):
                divergences.append(
                    {
                        "type": "size_mismatch",
                        "severity": "warning",
                        "symbol": symbol,
                        "localPositionIds": local_ids,
                        "localSize": local_size,
                        "exchangeSize": exchange_size,
                        "message": f"Local and exchange sizes differ for {symbol}.",
                    }
                )
            local_entry = float(position["entryPrice"])
            remote_entry = float(remote["entryPrice"])
            if local_entry and abs(local_entry - remote_entry) / local_entry > ENTRY_PRICE_TOLERANCE:
                divergences.append(
                    {
                        "type": "entry_price_drift",
                        "severity": "warning",
                        "symbol": symbol,
                        "localPositionIds": local_ids,
                        "localEntryPrice": local_entry,
                        "exchangeEntryPrice": remote_entry,
                        "message": f"Local and exchange entry prices drift for {symbol}.",
                    }
                )

        for symbol in sorted(set(exchange) - set(local)):
            divergences.append(
                {
                    "type": "untracked_exchange_position",
                    "severity": "error",
                    "symbol": symbol,
                    "message": f"Exchange holds {symbol} without a local live position.",
                }
            )
        return divergences

    def _alert_on_change(self, wallet_id: str, divergences: list[dict[str, Any]]) -> None:
        previous = self.store.get_last_reconciliation(wallet_id)
        previous_set = {
            (item.get("type"), item.get("symbol"))
            for item in (previous or {}).get("divergences", [])
        }
        for divergence in divergences:
            key = (divergence.get("type"), divergence.get("symbol"))
            if key in previous_set:
                continue
            self.alert_engine.reconciliation_divergence(
                divergence["message"],
                divergence["severity"],
                wallet_id,
            )
