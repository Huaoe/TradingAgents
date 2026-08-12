"""FastAPI backend for the Hyperliquid trading agent frontend."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.models.backtest import BacktestRequest, BacktestResult
from backend.models.strategy import StrategyCreate, StrategyUpdate
from backend.services.backtest import run_backtest
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.signal_engine import generate_signal
from backend.services.strategy_store import StrategyStore
from tradingagents.llm_clients import model_catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the Hyperliquid Info client on startup.
    _ = HyperliquidClient()
    yield


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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


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
        signal = generate_signal(payload.symbol, strategy)
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        )
        return BacktestResult(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    store = StrategyStore()
    strategy = await asyncio.to_thread(store.create_strategy, payload)
    return strategy.model_dump()


@app.patch("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, payload: StrategyUpdate) -> dict[str, Any]:
    store = StrategyStore()
    strategy = await asyncio.to_thread(store.update_strategy, strategy_id, payload)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy.model_dump()


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str) -> dict[str, bool]:
    store = StrategyStore()
    deleted = await asyncio.to_thread(store.delete_strategy, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return {"deleted": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
