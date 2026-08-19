"""Network-free exchange reconciliation tests."""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.reconciliation import ReconciliationService, _size_matches


class FakeStore:
    def __init__(
        self,
        positions: list[dict],
        pending_orders: list[dict] | None = None,
    ) -> None:
        self.positions = positions
        self.pending_orders = pending_orders or []
        self.saved: list[dict] = []

    def list_open_positions(self, wallet_id: str) -> list[dict]:
        return self.positions

    def list_pending_orders(self, wallet_id: str, mode: str) -> list[dict]:
        return self.pending_orders

    def get_last_reconciliation(self, wallet_id: str) -> dict | None:
        return self.saved[-1] if self.saved else None

    def save_reconciliation(self, result: dict) -> dict:
        self.saved.append(result)
        return result


class FakeAlerts:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def reconciliation_divergence(
        self,
        message: str,
        severity: str,
        wallet_id: str,
        related_id: str | None = None,
    ) -> dict:
        self.messages.append((message, severity))
        return {}


class FakeClient:
    def __init__(self, state: dict, open_orders: list[dict] | None = None) -> None:
        self.state = state
        self.open_orders = open_orders or []

    def get_clearinghouse_state(self, address: str, *, force: bool = False) -> dict:
        return self.state

    def get_open_orders(self, address: str, *, force: bool = False) -> list[dict]:
        return self.open_orders


class FakeWallets:
    def get_wallet(self, wallet_id: str) -> SimpleNamespace:
        return SimpleNamespace(address="0xabc")


class FakePortfolio:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def is_live_enabled(self, wallet_id: str) -> bool:
        return self.enabled


def _position(
    symbol: str = "BTC",
    side: str = "Buy",
    size: float = 1.0,
    position_id: str = "pos-1",
) -> dict:
    return {
        "id": position_id,
        "symbol": symbol,
        "side": side,
        "size": size,
        "entryPrice": 100.0,
        "mode": "live",
    }


def _state(*positions: tuple[str, float, float]) -> dict:
    return {
        "assetPositions": [
            {
                "position": {"coin": symbol, "szi": str(size), "entryPx": str(entry)},
            }
            for symbol, size, entry in positions
        ]
    }


def test_reconciliation_classifies_divergences_without_mutating_local_positions():
    local = [_position()]
    store = FakeStore(local)
    alerts = FakeAlerts()
    service = ReconciliationService(
        client=FakeClient(_state(("ETH", -2.0, 200.0), ("BTC", -1.1, 110.0))),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(),
        alert_engine=alerts,
    )

    result = service.reconcile("wallet-1")

    types = {item["type"] for item in result["divergences"]}
    assert types == {
        "side_mismatch",
        "size_mismatch",
        "entry_price_drift",
        "untracked_exchange_position",
    }
    assert local == [_position()]
    assert result["status"] == "diverged"
    assert len(alerts.messages) == len(result["divergences"])


def test_reconciliation_alerts_only_when_divergence_set_changes():
    store = FakeStore([_position()])
    alerts = FakeAlerts()
    service = ReconciliationService(
        client=FakeClient(_state(("BTC", 1.2, 100.0))),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(),
        alert_engine=alerts,
    )

    service.reconcile("wallet-1")
    service.reconcile("wallet-1")

    assert len(alerts.messages) == 1


def test_reconciliation_aggregates_multiple_local_positions_by_symbol():
    local = [
        _position(size=0.6, position_id="pos-long-a"),
        _position(size=0.4, position_id="pos-long-b"),
    ]
    store = FakeStore(local)
    service = ReconciliationService(
        client=FakeClient(_state(("BTC", 0.5, 100.0))),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(),
        alert_engine=FakeAlerts(),
    )

    result = service.reconcile("wallet-1")

    size_divergence = next(
        item for item in result["divergences"] if item["type"] == "size_mismatch"
    )
    assert size_divergence["localSize"] == 1.0
    assert size_divergence["exchangeSize"] == 0.5
    assert size_divergence["localPositionIds"] == ["pos-long-a", "pos-long-b"]


def test_size_tolerance_has_relative_and_absolute_floor():
    assert _size_matches(1.001, 1.0)
    assert not _size_matches(1.002, 1.0)
    assert _size_matches(0.0000005, 0.0)


def test_reconciliation_api_failure_is_unavailable():
    class FailingClient(FakeClient):
        def get_clearinghouse_state(self, address: str, *, force: bool = False) -> dict:
            raise RuntimeError("exchange unavailable")

    store = FakeStore([])
    service = ReconciliationService(
        client=FailingClient({}),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(),
        alert_engine=FakeAlerts(),
    )

    result = service.reconcile("wallet-1")

    assert result["status"] == "unavailable"
    assert result["error"] == "exchange unavailable"
    assert store.saved[-1]["status"] == "unavailable"


def test_reconciliation_for_paper_wallet_is_not_applicable():
    store = FakeStore([])
    service = ReconciliationService(
        client=FakeClient({}),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(enabled=False),
        alert_engine=FakeAlerts(),
    )

    result = service.reconcile("wallet-1")

    assert result["status"] == "not_applicable"
    assert "not enabled" in result["error"]


def test_reconciliation_reports_order_divergences():
    local_order = {
        "id": "ord-local",
        "walletId": "wallet-1",
        "symbol": "BTC",
        "exchangeOrderId": "101",
        "mode": "live",
        "status": "resting",
    }
    store = FakeStore([], [local_order])
    service = ReconciliationService(
        client=FakeClient(
            _state(),
            [{"oid": 202, "coin": "ETH"}],
        ),
        store=store,
        wallet_store=FakeWallets(),
        portfolio_store=FakePortfolio(),
        alert_engine=FakeAlerts(),
    )

    result = service.reconcile("wallet-1")

    kinds = {item["type"] for item in result["divergences"]}
    assert kinds == {"local_order_missing_on_exchange", "untracked_exchange_order"}
