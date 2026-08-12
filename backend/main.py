"""FastAPI backend for the Hyperliquid trading agent frontend."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.signal_engine import generate_signal


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
        signal = generate_signal(payload.symbol, payload.strategy or {})
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
