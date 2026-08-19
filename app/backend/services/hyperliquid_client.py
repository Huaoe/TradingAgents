"""Hyperliquid read-only client for the TradingAgents backend."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from hyperliquid.info import Info


class HyperliquidClient:
    """Singleton wrapper around the Hyperliquid ``Info`` client."""

    _instance: HyperliquidClient | None = None
    _universe_cache: dict[str, list[dict[str, Any]]] = {}
    _universe_cache_expiry: dict[str, float] = {}
    _market_cache: dict[str, dict[str, Any]] = {}
    _market_cache_expiry: dict[str, float] = {}
    _cache_ttl_seconds = 10.0
    _max_funding_pages = 1_000

    def __new__(cls) -> HyperliquidClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._info = Info(skip_ws=True)
        return cls._instance

    @classmethod
    def _cached_markets(
        cls,
        key: str,
        loader,
    ) -> list[dict[str, Any]]:
        now = time.monotonic()
        if cls._universe_cache_expiry.get(key, 0.0) > now:
            return cls._universe_cache[key]
        markets = loader()
        cls._universe_cache[key] = markets
        cls._universe_cache_expiry[key] = now + cls._cache_ttl_seconds
        for market in markets:
            market_key = market["symbol"].upper()
            cls._market_cache[market_key] = market
            cls._market_cache_expiry[market_key] = now + cls._cache_ttl_seconds
        return markets

    @property
    def info(self) -> Info:
        return self._info

    def get_perp_markets(self) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            meta, ctxs = self.info.meta_and_asset_ctxs()
            markets: list[dict[str, Any]] = []
            for asset, ctx in zip(meta["universe"], ctxs, strict=False):
                coin = asset["name"]
                mark = float(ctx.get("markPx") or 0)
                mid = float(ctx.get("midPx") or 0)
                prev = float(ctx.get("prevDayPx") or 0)
                price = mid or mark
                change = ((price - prev) / prev * 100) if price and prev else 0.0
                markets.append(
                    {
                        "symbol": coin,
                        "name": f"{coin}-PERP",
                        "type": "perp",
                        "price": round(price, 8) if price else 0.0,
                        "change24h": round(change, 2),
                        "volume24h": float(ctx.get("dayNtlVlm") or 0),
                        "funding": float(ctx.get("funding") or 0),
                        "openInterest": float(ctx.get("openInterest") or 0),
                        "markPrice": float(ctx.get("markPx") or 0),
                        "oraclePrice": float(ctx.get("oraclePx") or 0),
                        "maxLeverage": int(asset.get("maxLeverage") or 1),
                    }
                )
            return markets

        return self._cached_markets("perp", load)

    def get_spot_markets(self) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            spot_meta, spot_ctxs = self.info.spot_meta_and_asset_ctxs()
            token_by_index = {t["index"]: t for t in spot_meta["tokens"]}
            markets: list[dict[str, Any]] = []
            for asset, ctx in zip(spot_meta["universe"], spot_ctxs, strict=False):
                base_idx, quote_idx = asset["tokens"]
                base = token_by_index[base_idx]["name"]
                quote = token_by_index[quote_idx]["name"]
                name = f"{base}/{quote}"
                symbol = asset["name"] or name
                mark = float(ctx.get("markPx") or 0)
                mid = float(ctx.get("midPx") or 0)
                prev = float(ctx.get("prevDayPx") or 0)
                price = mid or mark
                change = ((price - prev) / prev * 100) if price and prev else 0.0
                markets.append(
                    {
                        "symbol": symbol,
                        "name": name,
                        "type": "spot",
                        "price": round(price, 8) if price else 0.0,
                        "change24h": round(change, 2),
                        "volume24h": float(ctx.get("dayNtlVlm") or 0),
                        "funding": 0.0,
                        "openInterest": 0.0,
                        "markPrice": float(ctx.get("markPx") or 0),
                        "oraclePrice": float(ctx.get("markPx") or 0),
                        "maxLeverage": 1,
                    }
                )
            return markets

        return self._cached_markets("spot", load)

    def get_markets(self) -> list[dict[str, Any]]:
        return self.get_perp_markets() + self.get_spot_markets()

    def get_market(self, symbol: str) -> dict[str, Any] | None:
        key = symbol.upper()
        if self._market_cache_expiry.get(key, 0.0) > time.monotonic():
            return self._market_cache[key]
        self.get_perp_markets()
        if self._market_cache_expiry.get(key, 0.0) > time.monotonic():
            return self._market_cache[key]
        self.get_spot_markets()
        return self._market_cache.get(key)

    def get_candles(
        self,
        symbol: str,
        interval: str = "1h",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        if end_ms is None:
            end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if start_ms is None:
            start_ms = end_ms - 7 * 24 * 60 * 60 * 1000
        raw = self.info.candles_snapshot(symbol, interval, start_ms, end_ms)
        return [
            {
                "time": int(row["t"]),
                "open": float(row["o"]),
                "high": float(row["h"]),
                "low": float(row["l"]),
                "close": float(row["c"]),
                "volume": float(row["v"]),
                "symbol": str(row["s"]),
                "interval": str(row["i"]),
            }
            for row in raw
        ]

    def get_candles_dataframe(
        self,
        symbol: str,
        interval: str = "1h",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        candles = self.get_candles(symbol, interval, start_ms, end_ms)
        df = pd.DataFrame(candles)
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
        if end_ms is None:
            end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if start_ms is None:
            start_ms = end_ms - 30 * 24 * 60 * 60 * 1000
        rows: list[dict[str, Any]] = []
        cursor = start_ms
        for _ in range(self._max_funding_pages):
            if cursor > end_ms:
                break
            raw = self.info.funding_history(symbol, cursor, end_ms)
            if not raw:
                break
            page = [
                {
                    "time": int(row["time"]),
                    "coin": row["coin"],
                    "fundingRate": float(row["fundingRate"]),
                    "premium": float(row["premium"]),
                }
                for row in raw
            ]
            rows.extend(page)
            last_time = max(row["time"] for row in page)
            if last_time >= end_ms or last_time < cursor:
                break
            next_cursor = last_time + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
        unique = {row["time"]: row for row in rows}
        return [unique[key] for key in sorted(unique)]

    def get_orderbook(self, symbol: str, levels: int = 10) -> dict[str, Any]:
        raw = self.info.l2_snapshot(symbol)
        bids = raw["levels"][0]
        asks = raw["levels"][1]
        bids_top = bids[:levels]
        asks_top = asks[:levels]

        def aggregate(rows):
            total_size = sum(float(r["sz"]) for r in rows)
            notional = sum(float(r["px"]) * float(r["sz"]) for r in rows)
            avg_px = notional / total_size if total_size else 0
            return {
                "count": len(rows),
                "totalSize": round(total_size, 8),
                "notional": round(notional, 2),
                "avgPrice": round(avg_px, 8),
                "top": [{"price": float(r["px"]), "size": float(r["sz"])} for r in rows[:5]],
            }

        return {
            "symbol": raw["coin"],
            "time": int(raw["time"]),
            "bid": aggregate(bids_top),
            "ask": aggregate(asks_top),
            "spreadPct": self._spread_pct(bids_top, asks_top),
            "imbalance": self._imbalance(bids_top, asks_top),
        }

    @staticmethod
    def _spread_pct(bids: list[dict], asks: list[dict]) -> float | None:
        if not bids or not asks:
            return None
        best_bid = float(bids[0]["px"])
        best_ask = float(asks[0]["px"])
        mid = (best_bid + best_ask) / 2
        if mid == 0:
            return None
        return round((best_ask - best_bid) / mid * 100, 4)

    @staticmethod
    def _imbalance(bids: list[dict], asks: list[dict]) -> float | None:
        bid_notional = sum(float(r["px"]) * float(r["sz"]) for r in bids)
        ask_notional = sum(float(r["px"]) * float(r["sz"]) for r in asks)
        total = bid_notional + ask_notional
        if total == 0:
            return None
        return round(bid_notional / total, 4)


# Module-level convenience functions
def client() -> HyperliquidClient:
    return HyperliquidClient()
