"""SQLite-backed store for trading strategies."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from backend.models.strategy import Strategy, StrategyCreate, StrategyUpdate

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "template-momentum-breakout",
        "name": "Momentum Breakout",
        "description": "Volume-confirmed breakouts with rising OI and neutral/positive funding. Trailing stop bias.",
        "template": "momentum_breakout",
        "agents": ["Market", "Sentiment", "News"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 5,
            "allocation": 0.15,
            "confidenceFloor": 65,
        },
    },
    {
        "id": "template-mean-reversion",
        "name": "Mean Reversion",
        "description": "RSI/MACD extremes and liquidation wicks with a tight stop.",
        "template": "mean_reversion",
        "agents": ["Market", "Sentiment"],
        "llmProvider": "anthropic",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.001,
            "shortFundingThreshold": 0.001,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-funding-rate-arb",
        "name": "Funding Rate Arb",
        "description": "Fade funding extremes vs. spot; OI divergence and pair-trade setups.",
        "template": "funding_rate_arb",
        "agents": ["Market", "Funding"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "deep",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0015,
            "shortFundingThreshold": 0.0015,
            "leverage": 2,
            "allocation": 0.20,
            "confidenceFloor": 70,
        },
    },
    {
        "id": "template-hype-delta-neutral",
        "name": "HYPE Delta Neutral",
        "description": "Long perp + short spot (or inverse) to harvest funding while keeping delta near zero.",
        "template": "hype_delta_neutral",
        "agents": ["Market", "Funding"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "deep",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.002,
            "shortFundingThreshold": 0.002,
            "leverage": 1,
            "allocation": 0.25,
            "confidenceFloor": 75,
        },
    },
    {
        "id": "template-trend-following",
        "name": "Trend Following",
        "description": "SMA/EMA aligned trends with momentum confirmation and funding filter.",
        "template": "trend_following",
        "agents": ["Market", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 4,
            "allocation": 0.12,
            "confidenceFloor": 62,
        },
    },
    {
        "id": "template-scalp-momentum",
        "name": "Scalp Momentum",
        "description": "Short-term Bollinger breakouts with tight stops and volume bias.",
        "template": "scalp_momentum",
        "agents": ["Market", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 6,
            "allocation": 0.08,
            "confidenceFloor": 68,
        },
    },
    {
        "id": "template-news-event",
        "name": "News Event",
        "description": "React to large catalyst-driven range bars using News and Sentiment agents.",
        "template": "news_event",
        "agents": ["News", "Sentiment", "Market"],
        "llmProvider": "anthropic",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 4,
            "allocation": 0.10,
            "confidenceFloor": 70,
        },
    },
    {
        "id": "template-basis-arbitrage",
        "name": "Basis Arbitrage",
        "description": "Fade perp funding extremes as a proxy for spot/perp basis convergence.",
        "template": "basis_arbitrage",
        "agents": ["Market", "Funding"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "deep",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 2,
            "allocation": 0.30,
            "confidenceFloor": 75,
        },
    },
    {
        "id": "template-grid-trading",
        "name": "Grid Trading",
        "description": "Range-bound grid: buy near the bottom of the recent range, sell/short near the top. Adapted from FMZ's classic grid strategies.",
        "template": "grid_trading",
        "agents": ["Market", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 2,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-dual-thrust",
        "name": "Dual Thrust",
        "description": "Classic FMZ range-breakout system: enter long/short when price clears an asymmetric band built from recent high/low/close range around the bar open.",
        "template": "dual_thrust",
        "agents": ["Market", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.12,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-turtle-breakout",
        "name": "Turtle Breakout",
        "description": "Donchian-channel breakout in the spirit of the Turtle Trading system: go long on new N-period highs, short on new N-period lows.",
        "template": "turtle_breakout",
        "agents": ["Market", "Funding"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.12,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-ema-bands-trend-catch",
        "name": "EMA Bands Trend Catch",
        "description": "Trend-following / counter-trend hybrid using EMA bands on highs/lows with Bollinger/RSI exhaustion exits. Adapted from FMZ's EMA-bands-leledc-bollinger-bands-trend-catching-strategy.",
        "template": "ema_bands_trend_catch",
        "agents": ["Market", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.12,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-atr-rsi-combo",
        "name": "ATR-RSI Combo",
        "description": "Volatility expansion filtered mean-reversion: enter when ATR breaks above its 20-period average and RSI is in an extreme zone. Adapted from FMZ's ATR-RSI组合策略.",
        "template": "atr_rsi_combo",
        "agents": ["Market", "Sentiment"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-time-series-momentum",
        "name": "Time Series Momentum",
        "description": "Go long/short based on the sign of the trailing N-bar return, the classic Moskowitz/Ooi/Pedersen time-series momentum effect. Adapted from paperswithbacktest/awesome-systematic-trading's Time Series Momentum Effect.",
        "template": "time_series_momentum",
        "agents": ["Market", "Funding"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.12,
            "confidenceFloor": 60,
        },
    },
    {
        "id": "template-overnight-seasonality-btc",
        "name": "Overnight Seasonality (BTC)",
        "description": "Long-only intraday seasonality: open a long position during the 22:00-23:59 UTC window and stay flat otherwise. Adapted from paperswithbacktest/awesome-systematic-trading's Intraday Seasonality in Bitcoin.",
        "template": "overnight_seasonality_btc",
        "agents": ["Market"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 2,
            "allocation": 0.10,
            "confidenceFloor": 65,
        },
    },
    {
        "id": "template-custom",
        "name": "Custom",
        "description": "Blank strategy; configure markets, agents, model, and risk manually.",
        "template": "custom",
        "agents": ["Market", "Funding", "OrderBook"],
        "llmProvider": "glm",
        "llmModel": "glm-5-turbo",
        "llmMode": "quick",
        "executionMode": "manual",
        "riskConfig": {
            "longFundingThreshold": -0.0005,
            "shortFundingThreshold": 0.0005,
            "leverage": 3,
            "allocation": 0.10,
            "confidenceFloor": 60,
        },
    },
]


def _default_timestamps() -> tuple[str, str]:
    now = _utc_now()
    return now, now


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class StrategyStore:
    """Singleton SQLite-backed store for strategies."""

    _instance: StrategyStore | None = None

    def __new__(cls, db_path: str | None = None) -> StrategyStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            path = db_path or str(Path(__file__).parent.parent / "data" / "strategies.db")
            cls._instance._db_path = path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            cls._instance._init_db()
            cls._instance._seed_templates()
        return cls._instance

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _seed_templates(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            for template in TEMPLATES:
                existing = conn.execute(
                    "SELECT 1 FROM strategies WHERE id = ?", (template["id"],)
                ).fetchone()
                if existing:
                    continue
                now = _utc_now()
                record = {
                    **template,
                    "markets": [],
                    "schedule": "",
                    "description": template["description"],
                    "createdAt": now,
                    "updatedAt": now,
                }
                conn.execute(
                    "INSERT INTO strategies (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (template["id"], json.dumps(record), now, now),
                )

    def list_strategies(self) -> list[Strategy]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT data FROM strategies ORDER BY created_at DESC").fetchall()
        return [Strategy(**json.loads(row[0])) for row in rows]

    def get_strategy(self, strategy_id: str) -> Strategy | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT data FROM strategies WHERE id = ?", (strategy_id,)
            ).fetchone()
        if not row:
            return None
        return Strategy(**json.loads(row[0]))

    def create_strategy(self, payload: StrategyCreate) -> Strategy:
        now = _utc_now()
        strategy_id = str(uuid.uuid4())
        data = payload.model_dump()
        data["id"] = strategy_id
        data["createdAt"] = now
        data["updatedAt"] = now
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO strategies (id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (strategy_id, json.dumps(data), now, now),
            )
        return Strategy(**data)

    def update_strategy(self, strategy_id: str, payload: StrategyUpdate) -> Strategy | None:
        existing = self.get_strategy(strategy_id)
        if not existing:
            return None
        update_data = existing.model_dump()
        for key, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                update_data[key] = value
        update_data["updatedAt"] = _utc_now()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE strategies SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(update_data), update_data["updatedAt"], strategy_id),
            )
        return Strategy(**update_data)

    def delete_strategy(self, strategy_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
            return cursor.rowcount > 0


def get_strategy_store() -> StrategyStore:
    return StrategyStore()
