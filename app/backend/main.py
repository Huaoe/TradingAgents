"""FastAPI backend for the Hyperliquid trading agent frontend."""

from __future__ import annotations

import asyncio
import logging
import os
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
from backend.models.signal import SignalCreate
from backend.models.strategy import StrategyCreate, StrategyUpdate
from backend.models.wallet import WalletCreate, WalletUpdate
from backend.services.alert_engine import AlertEngine
from backend.services.backtest import run_backtest
from backend.services.execution_engine import ExecutionEngine
from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.portfolio_engine import PortfolioEngine
from backend.services.signal_engine import generate_signal
from backend.services.signal_store import SignalStore
from backend.services.strategy_store import StrategyStore
from backend.services.wallet_store import WalletStore

logger = logging.getLogger(__name__)

# In-memory observability counters.  Persistent totals are read from the
# individual stores so metrics survive restarts where data is stored.
_METRICS: dict[str, int] = {"backtests_run": 0}

REFRESH_INTERVAL = 10
HISTORY_INTERVAL = 60


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the Hyperliquid Info client on startup.
    _ = HyperliquidClient()
    refresh_task = asyncio.create_task(_refresh_positions_loop())
    history_task = asyncio.create_task(_record_history_loop())
    try:
        yield
    finally:
        refresh_task.cancel()
        history_task.cancel()
        with suppress(asyncio.CancelledError):
            await refresh_task
        with suppress(asyncio.CancelledError):
            await history_task


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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


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


@app.get("/api/candles/{symbol}")
async def candles(symbol: str, interval: str = "1h") -> list[dict[str, Any]]:
    return HyperliquidClient().get_candles(symbol, interval)


@app.get("/api/orderbook/{symbol}")
async def orderbook(symbol: str) -> dict[str, Any]:
    return HyperliquidClient().get_orderbook(symbol)


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
