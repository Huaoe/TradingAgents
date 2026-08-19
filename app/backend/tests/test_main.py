"""API-level tests for the FastAPI backend."""

from __future__ import annotations

import httpx
import pytest

import backend.main as main_module
import backend.services.execution_store as execution_store_module
from backend.services.execution_store import ExecutionStore


@pytest.mark.anyio
async def test_health_with_httpx(app, mock_hyperliquid_client, isolated_stores):
    """Smoke-test the ASGI app directly with httpx."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["network"] in {"mainnet", "testnet"}
        assert "time" in body


def test_health_and_metrics(test_client):
    response = test_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["network"] in {"mainnet", "testnet"}
    assert "time" in body

    response = test_client.get("/api/metrics")
    assert response.status_code == 200
    body = response.json()
    expected_keys = {
        "total_backtests_run",
        "total_signals_generated",
        "total_orders_created",
        "total_wallets",
        "total_strategies",
        "open_positions_count",
    }
    assert expected_keys.issubset(set(body.keys()))
    assert body["total_backtests_run"] == 0


def test_health_reports_degraded_database(test_client, monkeypatch, tmp_path):
    monkeypatch.setattr(execution_store_module, "DB_PATH", str(tmp_path))
    main_module._HEALTH_CACHE = None

    response = test_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["sqlite"]["execution"]["status"] == "degraded"


def test_health_reports_degraded_hyperliquid(test_client, mock_hyperliquid_client, monkeypatch):
    def fail() -> list[dict]:
        raise RuntimeError("info unavailable")

    monkeypatch.setattr(mock_hyperliquid_client, "get_markets", fail)
    main_module._HEALTH_CACHE = None

    response = test_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["hyperliquid"]["status"] == "degraded"


@pytest.mark.parametrize("value", ["true", "1", "yes"])
def test_health_uses_shared_live_trading_gate(test_client, monkeypatch, value):
    monkeypatch.setenv("LIVE_TRADING", value)
    main_module._HEALTH_CACHE = None

    response = test_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["liveTradingEnabled"] is True


def test_metrics_update_with_activity(test_client):
    # Wallet
    wallet_payload = {
        "name": "metrics-wallet",
        "address": "0x" + "a" * 40,
        "chain": "hyperliquid",
        "isDefault": False,
        "privateKey": "0xdeadbeef",
        "masterPassword": "metrics-password",
    }
    response = test_client.post("/api/wallets", json=wallet_payload)
    assert response.status_code == 200

    # Signal
    signal_payload = {
        "symbol": "BTC",
        "strategy": {
            "template": "trend_following",
            "riskConfig": {
                "longFundingThreshold": -0.0005,
                "shortFundingThreshold": 0.0005,
                "leverage": 3,
                "allocation": 0.10,
                "confidenceFloor": 60,
            },
        },
    }
    response = test_client.post("/api/signals", json=signal_payload)
    assert response.status_code == 200

    # Backtest
    backtest_payload = {
        "symbol": "BTC",
        "interval": "1h",
        "startAt": "2024-01-01",
        "endAt": "2024-01-31",
        "strategy": signal_payload["strategy"],
        "initialBalance": 10_000.0,
    }
    response = test_client.post("/api/backtest", json=backtest_payload)
    assert response.status_code == 200

    # Order and position
    store = ExecutionStore()
    store.create_order(
        {
            "id": "ord-metrics01",
            "walletId": "wallet-metrics",
            "signalId": "sig-metrics01",
            "symbol": "BTC",
            "side": "Buy",
            "size": 0.1,
            "price": 100.0,
            "notional": 10.0,
            "leverage": 3,
            "fees": 0.01,
            "mode": "paper",
            "status": "filled",
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
    )
    store.create_position(
        {
            "id": "pos-metrics01",
            "orderId": "ord-metrics01",
            "walletId": "wallet-metrics",
            "symbol": "BTC",
            "side": "Buy",
            "entryPrice": 100.0,
            "markPrice": 101.0,
            "size": 0.1,
            "notional": 10.0,
            "leverage": 3,
            "pnl": 0.1,
            "pnlPct": 1.0,
            "margin": 3.33,
            "status": "open",
            "openedAt": "2024-01-01T00:00:00+00:00",
        }
    )

    response = test_client.get("/api/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["total_wallets"] == 1
    assert body["total_signals_generated"] == 1
    assert body["total_backtests_run"] == 1
    assert body["total_orders_created"] == 1
    assert body["open_positions_count"] == 1


def test_fee_and_slippage_estimate_routes(test_client):
    fees = test_client.get("/api/fees/0xabc")
    assert fees.status_code == 200
    assert fees.json()["makerFee"] == 0.00015
    assert fees.json()["takerFee"] == 0.00045

    estimate = test_client.get("/api/slippage-estimate/BTC?notional=3000")
    assert estimate.status_code == 200
    assert estimate.json()["slippagePct"] == 0.00005
    assert estimate.json()["source"] == "live_book"
