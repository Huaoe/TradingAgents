"""Shared fixtures for the TradingAgents backend test suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.main as main_module
import backend.services.backtest as backtest_module
import backend.services.execution_engine as execution_engine_module
import backend.services.hyperliquid_client as hyperliquid_client_module
import backend.services.portfolio_engine as portfolio_engine_module
import backend.services.reconciliation as reconciliation_module
import backend.services.signal_engine as signal_engine_module


def _utc_timestamp(year: int, month: int, day: int, hour: int = 0) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def make_candles(
    closes: list[float],
    start_time_ms: int | None = None,
    interval_ms: int = 3_600_000,
) -> list[dict[str, Any]]:
    """Build a list of OHLCV candle records from a sequence of closes."""
    if start_time_ms is None:
        start_time_ms = _utc_timestamp(2024, 1, 1, 0)
    candles: list[dict[str, Any]] = []
    for i, close in enumerate(closes):
        time = start_time_ms + i * interval_ms
        open_price = close - 1.0
        high = close + 1.0
        low = max(close - 1.0, 0.0)
        candles.append(
            {
                "time": time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000.0,
                "symbol": "BTC",
                "interval": "1h",
            }
        )
    return candles


class MockHyperliquidClient:
    """Network-free stand-in for the Hyperliquid read-only client."""

    _instance: MockHyperliquidClient | None = None

    def __new__(cls) -> MockHyperliquidClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def reset(self) -> None:
        self.market: dict[str, Any] = {
            "symbol": "BTC",
            "name": "BTC-PERP",
            "type": "perp",
            "price": 100.0,
            "change24h": 0.0,
            "volume24h": 1_000_000.0,
            "funding": 0.0,
            "openInterest": 100_000.0,
            "markPrice": 100.0,
            "oraclePrice": 100.0,
            "maxLeverage": 5,
        }
        self.markets: list[dict[str, Any]] = [self.market]
        self.orderbook: dict[str, Any] = {
            "symbol": "BTC",
            "time": 0,
            "bid": {"avgPrice": 99.5, "totalSize": 1.0},
            "ask": {"avgPrice": 100.5, "totalSize": 1.0},
            "spreadPct": 0.01,
            "imbalance": 0.5,
        }
        self.funding: list[dict[str, Any]] = []
        self.clearinghouse: dict[str, Any] = {
            "marginSummary": {
                "accountValue": "10000.0",
                "totalMarginUsed": "0.0",
                "withdrawable": "10000.0",
            },
            "assetPositions": [],
        }
        self.fills: list[dict[str, Any]] = []
        self.open_orders: list[dict[str, Any]] = []
        self.user_funding: list[dict[str, Any]] = []
        self.user_fees: dict[str, Any] = {
            "userCrossRate": "0.00045",
            "userAddRate": "0.00015",
            "userSpotCrossRate": "0.0004",
            "userSpotAddRate": "0.0002",
            "activeReferralDiscount": "0.0",
            "activeStakingDiscount": "0.0",
            "feeSchedule": {"tiers": []},
        }
        self.candles: list[dict[str, Any]] = make_candles([100.0 + i for i in range(100)])

    def get_markets(self) -> list[dict[str, Any]]:
        return self.markets

    def get_market(self, symbol: str) -> dict[str, Any] | None:
        for market in self.markets:
            if market.get("symbol", "").upper() == symbol.upper():
                return market
        return self.market

    def get_candles(
        self,
        symbol: str,
        interval: str = "1h",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.candles

    def get_candles_dataframe(
        self,
        symbol: str,
        interval: str = "1h",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        df = pd.DataFrame(self.candles)
        if df.empty:
            return df
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return df.sort_values("time")

    def get_funding_history(
        self,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.funding

    def get_orderbook(self, symbol: str, levels: int = 10) -> dict[str, Any]:
        return self.orderbook

    def get_user_fees(self, address: str) -> dict[str, Any]:
        return {
            "address": address,
            "makerFee": float(self.user_fees["userAddRate"]),
            "takerFee": float(self.user_fees["userCrossRate"]),
        }

    def estimate_slippage(self, symbol: str, notional: float) -> float:
        return 0.00005

    def get_clearinghouse_state(
        self,
        address: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        return self.clearinghouse

    def get_user_fills(
        self,
        address: str,
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        return self.fills

    def get_user_funding_history(
        self,
        address: str,
        start_ms: int,
        end_ms: int | None = None,
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        return self.user_funding

    def get_open_orders(
        self,
        address: str,
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        return self.open_orders


@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch, tmp_path):
    """Redirect all SQLite stores to a per-test temp directory."""
    import backend.services.alert_store as alert_store
    import backend.services.execution_store as execution_store
    import backend.services.llm_usage_store as llm_usage_store
    import backend.services.portfolio_engine as portfolio_engine
    import backend.services.signal_store as signal_store
    import backend.services.strategy_store as strategy_store
    import backend.services.wallet_store as wallet_store

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr(wallet_store, "DB_PATH", str(data_dir / "wallets.db"))
    monkeypatch.setattr(signal_store, "DB_PATH", str(data_dir / "signals.db"))
    monkeypatch.setattr(execution_store, "DB_PATH", str(data_dir / "execution.db"))
    monkeypatch.setattr(alert_store, "DB_PATH", str(data_dir / "alerts.db"))
    monkeypatch.setattr(portfolio_engine, "DB_PATH", str(data_dir / "portfolio.db"))
    monkeypatch.setattr(llm_usage_store, "DB_PATH", str(data_dir / "llm_usage.db"))
    monkeypatch.setattr(strategy_store, "DB_PATH", str(data_dir / "strategies.db"))

    # Reset singletons so the new DB paths are picked up.
    wallet_store.WalletStore._instance = None
    signal_store.SignalStore._instance = None
    execution_store.ExecutionStore._instance = None
    alert_store.AlertStore._instance = None
    portfolio_engine.PortfolioStore._instance = None
    llm_usage_store.LlmUsageStore._instance = None
    strategy_store.StrategyStore._instance = None

    # Prime the strategy store with its templates in the isolated DB.
    strategy_store.StrategyStore(db_path=str(data_dir / "strategies.db"))

    # Reset in-memory counters that are not tied to a store.
    main_module._METRICS["backtests_run"] = 0
    main_module._HEALTH_CACHE = None


@pytest.fixture
def mock_hyperliquid_client(monkeypatch, isolated_stores):
    """Replace the Hyperliquid client with a mock that never touches the network."""
    MockHyperliquidClient._instance = None
    mock = MockHyperliquidClient()
    mock.reset()

    # Patch every module that has a module-level HyperliquidClient name.
    monkeypatch.setattr(hyperliquid_client_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(main_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(backtest_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(signal_engine_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(execution_engine_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(portfolio_engine_module, "HyperliquidClient", MockHyperliquidClient)
    monkeypatch.setattr(reconciliation_module, "HyperliquidClient", MockHyperliquidClient)

    # Keep background refresh loops from firing during short-running tests.
    monkeypatch.setattr(main_module, "REFRESH_INTERVAL", 999_999)
    monkeypatch.setattr(main_module, "HISTORY_INTERVAL", 999_999)

    return mock


@pytest.fixture
def app(isolated_stores) -> FastAPI:
    return main_module.app


@pytest.fixture
def test_client(app, mock_hyperliquid_client, isolated_stores) -> TestClient:
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
