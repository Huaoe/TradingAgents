"""Tests for Hyperliquid metadata caching and funding pagination."""

from __future__ import annotations

import time

from backend.services.hyperliquid_client import HyperliquidClient


class _FundingInfo:
    def __init__(self):
        self.calls: list[int] = []

    def funding_history(self, symbol, start_ms, end_ms):
        self.calls.append(start_ms)
        if len(self.calls) == 1:
            return [
                {"time": 100, "coin": symbol, "fundingRate": "0.01", "premium": "0"},
                {"time": 200, "coin": symbol, "fundingRate": "0.02", "premium": "0"},
            ]
        return [
            {"time": 300, "coin": symbol, "fundingRate": "0.03", "premium": "0"},
        ]


def test_funding_history_pages_past_api_limit(monkeypatch):
    client = object.__new__(HyperliquidClient)
    info = _FundingInfo()
    client._info = info

    rows = client.get_funding_history("BTC", start_ms=0, end_ms=300)

    assert [row["time"] for row in rows] == [100, 200, 300]
    assert info.calls == [0, 201]


def test_get_market_uses_keyed_cache(monkeypatch):
    client = object.__new__(HyperliquidClient)
    key = "BTC"
    market = {"symbol": key, "type": "perp"}
    HyperliquidClient._market_cache[key] = market
    HyperliquidClient._market_cache_expiry[key] = time.monotonic() + 60
    calls = {"perp": 0, "spot": 0}

    def unexpected_perp():
        calls["perp"] += 1
        return []

    def unexpected_spot():
        calls["spot"] += 1
        return []

    monkeypatch.setattr(client, "get_perp_markets", unexpected_perp)
    monkeypatch.setattr(client, "get_spot_markets", unexpected_spot)

    assert client.get_market(key) == market
    assert calls == {"perp": 0, "spot": 0}
