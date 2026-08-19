"""Tests for Hyperliquid metadata caching and funding pagination."""

from __future__ import annotations

import time

import backend.services.hyperliquid_client as hyperliquid_client_module
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.hyperliquid_config import get_hyperliquid_base_url, get_hyperliquid_network


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


class _StuckFundingInfo:
    def __init__(self):
        self.calls = 0

    def funding_history(self, symbol, start_ms, end_ms):
        self.calls += 1
        return [{"time": start_ms, "coin": symbol, "fundingRate": "0.01", "premium": "0"}]


class _UserFeesInfo:
    def __init__(self):
        self.calls = 0

    def user_fees(self, address):
        self.calls += 1
        return {
            "userCrossRate": "0.0004",
            "userAddRate": "0.0001",
            "userSpotCrossRate": "0.0003",
            "userSpotAddRate": "0.0002",
            "activeReferralDiscount": "0.1",
            "activeStakingDiscount": "0.2",
            "feeSchedule": {"tiers": [{"maker": "0.0001"}]},
        }


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


def test_funding_history_has_a_page_limit():
    client = object.__new__(HyperliquidClient)
    info = _StuckFundingInfo()
    client._info = info
    client._max_funding_pages = 3

    client.get_funding_history("BTC", start_ms=0, end_ms=100)

    assert info.calls == 3


def test_user_fees_are_keyed_and_cached():
    client = object.__new__(HyperliquidClient)
    info = _UserFeesInfo()
    client._info = info
    first = client.get_user_fees("0xABC")
    second = client.get_user_fees("0xabc")

    assert first["makerFee"] == 0.0001
    assert first["takerFee"] == 0.0004
    assert first["userAddRate"] == 0.0001
    assert first["userCrossRate"] == 0.0004
    assert first["feeSchedule"]["tiers"]
    assert second == first
    assert info.calls == 1


def test_network_resolution_defaults_to_testnet(monkeypatch):
    monkeypatch.delenv("HYPERLIQUID_NETWORK", raising=False)
    assert get_hyperliquid_network() == "testnet"
    assert get_hyperliquid_base_url() != get_hyperliquid_base_url("mainnet")


def test_client_rebuilds_info_and_caches_when_network_changes(monkeypatch):
    calls = []

    class FakeInfo:
        def __init__(self, base_url, skip_ws):
            calls.append((base_url, skip_ws))

    monkeypatch.setattr(hyperliquid_client_module, "Info", FakeInfo)
    HyperliquidClient._instance = None
    HyperliquidClient._clear_caches()

    monkeypatch.setenv("HYPERLIQUID_NETWORK", "testnet")
    first = HyperliquidClient()
    HyperliquidClient._market_cache["BTC"] = {"symbol": "BTC", "network": "testnet"}
    HyperliquidClient._market_cache_expiry["BTC"] = time.monotonic() + 60

    monkeypatch.setenv("HYPERLIQUID_NETWORK", "mainnet")
    second = HyperliquidClient()

    assert first is second
    assert calls == [
        (get_hyperliquid_base_url("testnet"), True),
        (get_hyperliquid_base_url("mainnet"), True),
    ]
    assert "BTC" not in HyperliquidClient._market_cache
