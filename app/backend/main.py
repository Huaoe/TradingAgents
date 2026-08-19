"""FastAPI backend for the Hyperliquid trading agent frontend."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from tradingagents.llm_clients import model_catalog

from backend.models.alert import AlertReadRequest
from backend.models.backtest import BacktestRequest, BacktestResult
from backend.models.execution import ClosePositionRequest, ExecuteRequest
from backend.models.portfolio import LiveModeRequest, PortfolioSummary
from backend.models.reconciliation import ReconcileRequest, ReconciliationResult
from backend.models.signal import SignalCreate
from backend.models.strategy import StrategyCreate, StrategyUpdate
from backend.models.strategy_search import StrategySearchJob, StrategySearchRequest
from backend.models.wallet import WalletCreate, WalletUpdate
from backend.services.alert_engine import AlertEngine
from backend.services.backtest import run_backtest
from backend.services.execution_engine import ExecutionEngine
from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.hyperliquid_config import get_hyperliquid_network
from backend.services.portfolio_engine import PortfolioEngine
from backend.services.reconciliation import ReconciliationService
from backend.services.signal_engine import generate_signal
from backend.services.signal_store import SignalStore
from backend.services.strategy_search import (
    prepare_strategy_search,
    run_strategy_search,
    simulation_count,
)
from backend.services.strategy_store import StrategyStore
from backend.services.wallet_store import WalletStore

logger = logging.getLogger(__name__)

# In-memory observability counters.  Persistent totals are read from the
# individual stores so metrics survive restarts where data is stored.
_METRICS: dict[str, int] = {"backtests_run": 0}
_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_SEARCH_JOBS_LOCK = threading.Lock()
_MAX_SEARCH_JOBS = 5

REFRESH_INTERVAL = 10
HISTORY_INTERVAL = 60
RECONCILIATION_INTERVAL = 60
HEALTH_CACHE_SECONDS = 5
_HEALTH_CACHE: tuple[float, dict[str, Any]] | None = None


async def _refresh_positions_loop() -> None:
    engine = ExecutionEngine()
    while True:
        try:
            await asyncio.to_thread(engine.refresh_positions)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Position refresh failed: %s", exc)
        await asyncio.sleep(REFRESH_INTERVAL)


async def _record_history_loop() -> None:
    engine = PortfolioEngine()
    while True:
        await asyncio.sleep(HISTORY_INTERVAL)
        try:
            await asyncio.to_thread(engine.record_history)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Portfolio history snapshot failed: %s", exc)


async def _reconciliation_loop() -> None:
    service = ReconciliationService()
    portfolio_store = PortfolioEngine().portfolio_store
    wallet_store = WalletStore()
    while True:
        try:
            for wallet_id in portfolio_store.list_live_wallet_ids():
                wallet = wallet_store.get_wallet(wallet_id)
                if wallet:
                    await asyncio.to_thread(service.reconcile, wallet_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation loop failed: %s", exc)
        await asyncio.sleep(RECONCILIATION_INTERVAL)


def _health_result() -> dict[str, Any]:
    global _HEALTH_CACHE
    now = time.monotonic()
    if _HEALTH_CACHE and _HEALTH_CACHE[0] > now:
        return _HEALTH_CACHE[1]

    from backend.services import (
        alert_store,
        execution_store,
        llm_usage_store,
        portfolio_engine,
        signal_store,
        wallet_store,
    )

    sqlite_paths = {
        "alerts": alert_store.DB_PATH,
        "execution": execution_store.DB_PATH,
        "llmUsage": llm_usage_store.DB_PATH,
        "portfolio": portfolio_engine.DB_PATH,
        "signals": signal_store.DB_PATH,
        "strategies": str(Path(__file__).parent / "data" / "strategies.db"),
        "wallets": wallet_store.DB_PATH,
    }
    sqlite_status: dict[str, Any] = {}
    for name, path in sqlite_paths.items():
        try:
            if not os.path.exists(path):
                sqlite_status[name] = {"status": "ok", "detail": "not initialized"}
                continue
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                conn.execute("SELECT 1").fetchone()
            sqlite_status[name] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            sqlite_status[name] = {"status": "degraded", "error": str(exc)}

    client = HyperliquidClient()
    try:
        client.get_markets()
        hyperliquid = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        hyperliquid = {"status": "degraded", "error": str(exc)}
    dependencies = {"sqlite": sqlite_status, "hyperliquid": hyperliquid}
    db_ok = all(item["status"] == "ok" for item in sqlite_status.values())
    result = {
        "status": "ok" if db_ok and hyperliquid["status"] == "ok" else "degraded",
        "network": get_hyperliquid_network(),
        "liveTradingEnabled": os.getenv("LIVE_TRADING", "").lower() == "true",
        "dependencies": dependencies,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    _HEALTH_CACHE = (now + HEALTH_CACHE_SECONDS, result)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the Hyperliquid Info client on startup.
    _ = HyperliquidClient()
    refresh_task = asyncio.create_task(_refresh_positions_loop())
    history_task = asyncio.create_task(_record_history_loop())
    reconciliation_task = asyncio.create_task(_reconciliation_loop())
    try:
        yield
    finally:
        refresh_task.cancel()
        history_task.cancel()
        reconciliation_task.cancel()
        with suppress(asyncio.CancelledError):
            await refresh_task
        with suppress(asyncio.CancelledError):
            await history_task
        with suppress(asyncio.CancelledError):
            await reconciliation_task


app = FastAPI(
    title="Hyperliquid Trading Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    symbol: str
    strategy: dict[str, Any] | None = None
    strategyId: str | None = None
    useLlm: bool = False


def _search_progress(job_id: str, completed: int, total: int) -> None:
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS.get(job_id)
        if job:
            job["progress"] = {"completed": completed, "total": total}


def _run_search_job(
    job_id: str,
    payload: StrategySearchRequest,
    frame: Any,
    max_leverage: int,
) -> None:
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
    try:
        result = run_strategy_search(
            symbol=payload.symbol,
            interval=payload.interval,
            start_at=payload.startAt,
            end_at=payload.endAt,
            templates=payload.templates,
            folds=payload.folds,
            min_trades_is=payload.minTradesIS,
            grid_preset=payload.gridPreset,
            initial_balance=payload.initialBalance,
            maker_fee=payload.makerFee,
            taker_fee=payload.takerFee,
            slippage_pct=payload.slippagePct,
            order_type=payload.orderType,
            fee_source=payload.feeSource,
            slippage_source=payload.slippageSource,
            progress=lambda completed, total: _search_progress(job_id, completed, total),
            prepared_frame=frame,
            prepared_max_leverage=max_leverage,
        )
        with _SEARCH_JOBS_LOCK:
            job = _SEARCH_JOBS.get(job_id)
            if job:
                job["status"] = "done"
                job["result"] = result
                job["progress"] = {
                    "completed": job["progress"]["total"],
                    "total": job["progress"]["total"],
                }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Strategy search failed: %s", exc)
        with _SEARCH_JOBS_LOCK:
            job = _SEARCH_JOBS.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = str(exc)


def _search_job_response(job_id: str) -> StrategySearchJob:
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Strategy search {job_id} not found")
        return StrategySearchJob(**job)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return await asyncio.to_thread(_health_result)


@app.post("/api/reconcile", response_model=ReconciliationResult)
async def reconcile(payload: ReconcileRequest) -> ReconciliationResult:
    result = await asyncio.to_thread(ReconciliationService().reconcile, payload.walletId)
    return ReconciliationResult(**result)


@app.get("/api/reconcile", response_model=ReconciliationResult | None)
async def last_reconciliation(wallet_id: str) -> ReconciliationResult | None:
    result = await asyncio.to_thread(
        ExecutionStore().get_last_reconciliation,
        wallet_id,
    )
    return ReconciliationResult(**result) if result else None


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    return {
        "total_backtests_run": _METRICS["backtests_run"],
        "total_signals_generated": len(SignalStore().list_signals()),
        "total_orders_created": len(ExecutionStore().list_orders()),
        "total_wallets": len(WalletStore().list_wallets()),
        "total_strategies": len(StrategyStore().list_strategies()),
        "open_positions_count": len(
            [p for p in ExecutionStore().list_positions() if p["status"] == "open"]
        ),
    }


@app.get("/api/markets")
async def markets() -> list[dict[str, Any]]:
    return HyperliquidClient().get_markets()


@app.get("/api/markets/{symbol}")
async def market_detail(symbol: str) -> dict[str, Any]:
    market = HyperliquidClient().get_market(symbol)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market {symbol} not found")
    return market


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest) -> dict[str, Any]:
    try:
        strategy = payload.strategy or {}
        if payload.strategyId:
            store = StrategyStore()
            stored = await asyncio.to_thread(store.get_strategy, payload.strategyId)
            if stored:
                strategy = {**stored.riskConfig.model_dump(), **strategy}
            else:
                raise HTTPException(
                    status_code=404, detail=f"Strategy {payload.strategyId} not found"
                )
        signal = generate_signal(payload.symbol, strategy, use_llm=payload.useLlm)
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/signals")
async def create_signal(payload: SignalCreate) -> dict[str, Any]:
    try:
        strategy: dict[str, Any] = payload.strategy or {}
        if payload.strategyId:
            store = StrategyStore()
            stored = await asyncio.to_thread(store.get_strategy, payload.strategyId)
            if stored:
                strategy = {**stored.riskConfig.model_dump(), **strategy}
            else:
                raise HTTPException(
                    status_code=404, detail=f"Strategy {payload.strategyId} not found"
                )
        signal = generate_signal(payload.symbol, strategy, use_llm=payload.useLlm)
        signal_store = SignalStore()
        await asyncio.to_thread(signal_store.store_signal, signal)
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/signals")
async def list_signals(limit: int = 100) -> list[dict[str, Any]]:
    store = SignalStore()
    return await asyncio.to_thread(store.list_signals, limit)


@app.get("/api/signals/{signal_id}")
async def get_signal(signal_id: str) -> dict[str, Any]:
    store = SignalStore()
    signal = await asyncio.to_thread(store.get_signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return signal


@app.patch("/api/signals/{signal_id}")
async def update_signal_status(signal_id: str, status: dict[str, Any]) -> dict[str, Any]:
    store = SignalStore()
    signal = await asyncio.to_thread(store.get_signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    new_status = status.get("status")
    if new_status not in ("pending", "accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status")
    await asyncio.to_thread(store.update_status, signal_id, new_status)
    signal["status"] = new_status
    return signal


@app.delete("/api/signals/{signal_id}")
async def delete_signal(signal_id: str) -> dict[str, bool]:
    store = SignalStore()
    deleted = await asyncio.to_thread(store.delete_signal, signal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return {"deleted": True}


@app.post("/api/backtest")
async def backtest(payload: BacktestRequest) -> BacktestResult:
    try:
        strategy: dict[str, Any] = payload.strategy or {}
        if payload.strategyId:
            store = StrategyStore()
            stored = await asyncio.to_thread(store.get_strategy, payload.strategyId)
            if stored:
                strategy = {**stored.model_dump(), **strategy}
            else:
                raise HTTPException(
                    status_code=404, detail=f"Strategy {payload.strategyId} not found"
                )
        result = run_backtest(
            symbol=payload.symbol,
            interval=payload.interval,
            start_at=payload.startAt,
            end_at=payload.endAt,
            strategy=strategy,
            initial_balance=payload.initialBalance,
            maker_fee=payload.makerFee,
            taker_fee=payload.takerFee,
            slippage_pct=payload.slippagePct,
            order_type=payload.orderType,
            fee_source=payload.feeSource,
            slippage_source=payload.slippageSource,
        )
        _METRICS["backtests_run"] += 1
        return BacktestResult(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/strategy-search", response_model=StrategySearchJob)
async def strategy_search(payload: StrategySearchRequest) -> StrategySearchJob:
    try:
        frame, max_leverage, candidates, total = await asyncio.to_thread(
            prepare_strategy_search,
            payload.symbol,
            payload.interval,
            payload.startAt,
            payload.endAt,
            payload.templates,
            payload.folds,
            payload.gridPreset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not prepare strategy search: %s", exc)
        raise HTTPException(status_code=500, detail="Could not prepare strategy search") from exc

    job_id = str(uuid.uuid4())
    with _SEARCH_JOBS_LOCK:
        while len(_SEARCH_JOBS) >= _MAX_SEARCH_JOBS:
            oldest_id = next(iter(_SEARCH_JOBS))
            _SEARCH_JOBS.pop(oldest_id)
        _SEARCH_JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "candidateCount": len(candidates),
            "simulationCount": simulation_count(len(candidates), payload.folds),
            "progress": {"completed": 0, "total": total},
            "result": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_search_job,
        args=(job_id, payload, frame, max_leverage),
        name=f"strategy-search-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return _search_job_response(job_id)


@app.get("/api/strategy-search/{search_id}", response_model=StrategySearchJob)
async def strategy_search_status(search_id: str) -> StrategySearchJob:
    return _search_job_response(search_id)


@app.get("/api/candles/{symbol}")
async def candles(symbol: str, interval: str = "1h") -> list[dict[str, Any]]:
    return HyperliquidClient().get_candles(symbol, interval)


@app.get("/api/orderbook/{symbol}")
async def orderbook(symbol: str) -> dict[str, Any]:
    return HyperliquidClient().get_orderbook(symbol)


@app.get("/api/fees/{address}")
async def user_fees(address: str) -> dict[str, Any]:
    try:
        return HyperliquidClient().get_user_fees(address)
    except Exception as exc:
        logger.warning("Could not fetch Hyperliquid fees for %s: %s", address, exc)
        raise HTTPException(status_code=502, detail="Could not fetch wallet fee rates") from exc


@app.get("/api/slippage-estimate/{symbol}")
async def slippage_estimate(symbol: str, notional: float) -> dict[str, Any]:
    try:
        estimate = HyperliquidClient().estimate_slippage(symbol, notional)
        return {
            "symbol": symbol.upper(),
            "notional": notional,
            "slippagePct": estimate,
            "slippageBps": estimate * 10_000,
            "source": "live_book",
        }
    except Exception as exc:
        logger.warning("Could not estimate slippage for %s: %s", symbol, exc)
        raise HTTPException(status_code=502, detail="Could not estimate live-book slippage") from exc


@app.get("/api/funding/{symbol}")
async def funding(symbol: str) -> list[dict[str, Any]]:
    return HyperliquidClient().get_funding_history(symbol)


@app.get("/api/models")
async def models_catalog() -> dict[str, dict[str, list[dict[str, str]]]]:
    """Return provider -> mode -> list of {label, value} model options."""
    return {
        provider: {
            mode: [{"label": label, "value": value} for label, value in options]
            for mode, options in mode_options.items()
        }
        for provider, mode_options in model_catalog.MODEL_OPTIONS.items()
    }


@app.get("/api/strategies")
async def list_strategies() -> list[dict[str, Any]]:
    store = StrategyStore()
    strategies = await asyncio.to_thread(store.list_strategies)
    return [s.model_dump() for s in strategies]


@app.get("/api/strategies/{strategy_id}")
async def get_strategy(strategy_id: str) -> dict[str, Any]:
    store = StrategyStore()
    strategy = await asyncio.to_thread(store.get_strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy.model_dump()


@app.post("/api/strategies")
async def create_strategy(payload: StrategyCreate) -> dict[str, Any]:
    try:
        store = StrategyStore()
        strategy = await asyncio.to_thread(store.create_strategy, payload)
        return strategy.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error creating strategy: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.patch("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, payload: StrategyUpdate) -> dict[str, Any]:
    try:
        store = StrategyStore()
        strategy = await asyncio.to_thread(store.update_strategy, strategy_id, payload)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
        return strategy.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error updating strategy: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str) -> dict[str, bool]:
    store = StrategyStore()
    deleted = await asyncio.to_thread(store.delete_strategy, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return {"deleted": True}


@app.get("/api/wallets")
async def list_wallets() -> list[dict[str, Any]]:
    store = WalletStore()
    wallets = await asyncio.to_thread(store.list_wallets)
    return [w.to_dict() for w in wallets]


@app.get("/api/wallets/default")
async def get_default_wallet() -> dict[str, Any]:
    store = WalletStore()
    wallet = await asyncio.to_thread(store.get_default_wallet)
    if not wallet:
        raise HTTPException(status_code=404, detail="No default wallet configured")
    return wallet.to_dict()


@app.get("/api/wallets/{wallet_id}")
async def get_wallet(wallet_id: str) -> dict[str, Any]:
    store = WalletStore()
    wallet = await asyncio.to_thread(store.get_wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")
    return wallet.to_dict()


@app.post("/api/wallets")
async def create_wallet(payload: WalletCreate) -> dict[str, Any]:
    store = WalletStore()
    wallet = await asyncio.to_thread(store.create_wallet, payload)
    return wallet.to_dict()


@app.patch("/api/wallets/{wallet_id}")
async def update_wallet(wallet_id: str, payload: WalletUpdate) -> dict[str, Any]:
    store = WalletStore()
    wallet = await asyncio.to_thread(store.update_wallet, wallet_id, payload)
    if not wallet:
        raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")
    return wallet.to_dict()


@app.delete("/api/wallets/{wallet_id}")
async def delete_wallet(wallet_id: str) -> dict[str, bool]:
    store = WalletStore()
    deleted = await asyncio.to_thread(store.delete_wallet, wallet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")
    return {"deleted": True}


@app.post("/api/execute")
async def execute_trade(payload: ExecuteRequest) -> dict[str, Any]:
    try:
        engine = ExecutionEngine()
        result = await asyncio.to_thread(
            engine.execute,
            payload.signalId,
            payload.walletId,
            payload.mode,
            payload.masterPassword,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/positions")
async def list_positions(wallet_id: str | None = None) -> list[dict[str, Any]]:
    try:
        engine = ExecutionEngine()
        return await asyncio.to_thread(engine.list_positions, wallet_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/positions/{position_id}/close")
async def close_position(position_id: str, payload: ClosePositionRequest) -> dict[str, Any]:
    try:
        engine = ExecutionEngine()
        result = await asyncio.to_thread(
            engine.close_position,
            position_id,
            payload.walletId,
            payload.mode,
            payload.masterPassword,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/orders")
async def list_orders(wallet_id: str | None = None) -> list[dict[str, Any]]:
    try:
        engine = ExecutionEngine()
        return await asyncio.to_thread(engine.list_orders, wallet_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/portfolio")
async def portfolio(wallet_id: str | None = None) -> PortfolioSummary:
    try:
        engine = PortfolioEngine()
        result = await asyncio.to_thread(engine.summary, wallet_id)
        return PortfolioSummary(**result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/portfolio/history")
async def portfolio_history(wallet_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    try:
        engine = PortfolioEngine()
        return await asyncio.to_thread(engine.portfolio_store.get_history, wallet_id, limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/portfolio/live")
async def set_live_mode(payload: LiveModeRequest) -> dict[str, Any]:
    try:
        engine = PortfolioEngine()
        await asyncio.to_thread(
            engine.portfolio_store.set_live_enabled, payload.walletId, payload.enabled
        )
        return {"walletId": payload.walletId, "liveEnabled": payload.enabled}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/alerts")
async def list_alerts(
    wallet_id: str | None = None, unread_only: bool = False
) -> list[dict[str, Any]]:
    try:
        engine = AlertEngine()
        return await asyncio.to_thread(engine.list_alerts, wallet_id, unread_only)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/alerts/unread")
async def unread_alert_count(wallet_id: str | None = None) -> dict[str, Any]:
    try:
        engine = AlertEngine()
        count = await asyncio.to_thread(engine.unread_count, wallet_id)
        return {"unread": count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/alerts/{alert_id}/read")
async def read_alert(alert_id: str, payload: AlertReadRequest | None = None) -> dict[str, Any]:
    try:
        engine = AlertEngine()
        if payload is None:
            payload = AlertReadRequest()
        ok = await asyncio.to_thread(engine.mark_read, alert_id)
        return {"alertId": alert_id, "read": ok}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/alerts/read-all")
async def read_all_alerts(wallet_id: str | None = None) -> dict[str, Any]:
    try:
        engine = AlertEngine()
        ok = await asyncio.to_thread(engine.store.mark_all_read, wallet_id)
        return {"read": ok}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/journal")
async def list_journal(wallet_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    try:
        engine = AlertEngine()
        return await asyncio.to_thread(engine.list_journal, wallet_id, limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# Serve the built React app from the Docker image. API routes above take precedence.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str) -> Any:
    if not FRONTEND_DIST.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    file = FRONTEND_DIST / full_path
    if file.is_file():
        return FileResponse(file)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
