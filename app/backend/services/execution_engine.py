"""Trade execution engine for Hyperliquid (paper and live modes)."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from backend.models.wallet import Wallet
from backend.services.alert_engine import AlertEngine
from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.hyperliquid_config import (
    get_hyperliquid_base_url,
    is_live_trading_enabled,
)
from backend.services.portfolio_engine import PortfolioEngine
from backend.services.protective import evaluate_protective_exit, protective_levels
from backend.services.signal_store import SignalStore
from backend.services.wallet_store import WalletStore

# Hyperliquid taker fee at base tier.
TAKER_FEE = 0.00045
PAPER_SLIPPAGE = 0.0005
TRIGGER_SLIPPAGE = 0.01
FILL_LOOKUP_ATTEMPTS = 3
FILL_LOOKUP_DELAY_SECONDS = 0.2
PNL_DIVERGENCE_TOLERANCE = 0.01
logger = logging.getLogger(__name__)


def _side_for_signal(action: str) -> str:
    return "Buy" if action == "BUY" else "Sell" if action == "SELL" else "Hold"


def _liquidation_price(entry: float, leverage: int, side: str) -> float | None:
    if leverage <= 1 or entry <= 0:
        return None
    maintenance_margin = 0.01  # rough approximation
    if side == "Buy":
        return entry * (1 - (1 / leverage) + maintenance_margin)
    return entry * (1 + (1 / leverage) - maintenance_margin)


def _paper_fill(
    symbol: str,
    side: str,
    notional: float = 0.0,
    client: HyperliquidClient | None = None,
    slippage_pct: float | None = None,
) -> float:
    """Return a simulated fill price (slightly worse than mid)."""
    client = client or HyperliquidClient()
    market = client.get_market(symbol)
    price = market.get("price") or 0.0 if market else 0.0
    if not price:
        book = client.get_orderbook(symbol, levels=1)
        bids = book.get("bid", {})
        asks = book.get("ask", {})
        price = (
            (asks.get("avgPrice") or price) if side == "Buy" else (bids.get("avgPrice") or price)
        )
    slippage = PAPER_SLIPPAGE if slippage_pct is None else slippage_pct
    multiplier = 1 + slippage if side == "Buy" else 1 - slippage
    return round(float(price) * multiplier, 8)


def _exchange_order_id(result: dict[str, Any]) -> str | None:
    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
    if not statuses:
        return None
    status = statuses[0]
    for key in ("filled", "resting"):
        record = status.get(key)
        if isinstance(record, dict) and record.get("oid") is not None:
            return str(record["oid"])
    return None


def _fill_metrics(fills: list[dict[str, Any]]) -> dict[str, Any]:
    total_size = sum(float(fill.get("sz") or fill.get("size") or 0.0) for fill in fills)
    weighted_notional = sum(
        float(fill.get("px") or fill.get("price") or 0.0)
        * float(fill.get("sz") or fill.get("size") or 0.0)
        for fill in fills
    )
    return {
        "size": total_size,
        "price": weighted_notional / total_size if total_size else 0.0,
        "fees": sum(
            float(fill.get("fee") or fill.get("feeUsd") or 0.0)
            + float(fill.get("builderFee") or fill.get("builderFeeUsd") or 0.0)
            for fill in fills
        ),
        "closedPnl": sum(float(fill.get("closedPnl") or 0.0) for fill in fills),
    }


def _funding_paid(
    client: HyperliquidClient,
    address: str,
    symbol: str,
    opened_at: str,
    closed_at: str,
) -> tuple[float, list[dict[str, Any]]]:
    start_ms = int(datetime.fromisoformat(opened_at).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(closed_at).timestamp() * 1000)
    rows = client.get_user_funding_history(address, start_ms, end_ms)
    relevant = [row for row in rows if str(row.get("coin", "")).upper() == symbol.upper()]
    signed_cash_flow = sum(float(row.get("usdc") or row.get("amount") or 0.0) for row in relevant)
    return -signed_cash_flow, relevant


def _live_exchange(wallet: Wallet, private_key: str):
    """Build a Hyperliquid ``Exchange`` client from a decrypted private key."""
    import eth_account  # noqa: F401
    from hyperliquid.exchange import Exchange

    account = eth_account.Account.from_key(private_key)
    return Exchange(
        account,
        get_hyperliquid_base_url(),
        account_address=wallet.address,
    )


def _set_live_leverage(exchange: Any, symbol: str, leverage: int) -> None:
    """Set leverage and reject the order if Hyperliquid declines the update."""
    try:
        result = exchange.update_leverage(leverage, symbol, is_cross=True)
    except Exception as exc:
        raise ValueError(f"Could not set {symbol} leverage to {leverage}x: {exc}") from exc
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise ValueError(f"Could not set {symbol} leverage to {leverage}x: {result}")


class ExecutionEngine:
    """Execute persisted signals against Hyperliquid (paper or live)."""

    def __init__(self) -> None:
        self.store = ExecutionStore()
        self.signal_store = SignalStore()
        self.wallet_store = WalletStore()
        self.portfolio_engine = PortfolioEngine()
        self.alert_engine = AlertEngine()
        self.client = HyperliquidClient()

    def _fee_rate(self, address: str) -> tuple[float, str]:
        try:
            return float(self.client.get_user_fees(address)["takerFee"]), "wallet"
        except Exception:  # noqa: BLE001
            return TAKER_FEE, "generic_default"

    def _maker_fee_rate(self, address: str) -> tuple[float, str]:
        try:
            return float(self.client.get_user_fees(address)["makerFee"]), "wallet"
        except Exception:  # noqa: BLE001
            return 0.00015, "generic_default"

    def _best_limit_price(self, symbol: str, side: str) -> tuple[float, float, float]:
        book = self.client.get_orderbook(symbol, levels=1)
        bid = book.get("bid") or {}
        ask = book.get("ask") or {}
        best_bid = float((bid.get("top") or [{}])[0].get("price") or bid.get("avgPrice") or 0.0)
        best_ask = float((ask.get("top") or [{}])[0].get("price") or ask.get("avgPrice") or 0.0)
        if not best_bid or not best_ask:
            raise ValueError(f"Order book for {symbol} is empty")
        return (best_bid if side == "Buy" else best_ask), best_bid, best_ask

    @staticmethod
    def _validate_post_only_price(
        side: str,
        limit_price: float,
        best_bid: float,
        best_ask: float,
        tif: str,
    ) -> None:
        if not math.isfinite(limit_price) or limit_price <= 0:
            raise ValueError("limitPrice must be a positive finite number")
        if tif == "Alo" and (
            (side == "Buy" and limit_price >= best_ask)
            or (side == "Sell" and limit_price <= best_bid)
        ):
            raise ValueError(
                f"Alo limit price {limit_price:.8f} would cross the {side.lower()} side "
                f"of the book ({best_ask if side == 'Buy' else best_bid:.8f})"
            )

    @staticmethod
    def _expires_at(now: datetime, expire_minutes: float | None) -> str | None:
        if expire_minutes is None:
            return None
        if expire_minutes <= 0:
            raise ValueError("expireMinutes must be greater than zero")
        return (now + timedelta(minutes=expire_minutes)).isoformat()

    def _create_position_from_fill(
        self,
        order: dict[str, Any],
        fill_price: float,
        filled_size: float,
        wallet: Wallet,
        risk_config: dict[str, Any],
        exchange: Any | None = None,
    ) -> dict[str, Any]:
        """Create the same position state for market and deferred fills."""
        fill_notional = fill_price * filled_size
        order_meta = order.get("meta") or {}
        order_meta["fillPrice"] = fill_price
        order["meta"] = order_meta
        order["filledSize"] = max(float(order.get("filledSize") or 0.0), filled_size)
        if order["type"] == "Market":
            order["size"] = filled_size
            order["notional"] = round(fill_notional, 2)
        self.store.update_order(order)

        side = order["side"]
        protective = protective_levels(fill_price, side, risk_config)
        live_market = self.client.get_market(order["symbol"])
        live_mark = (
            live_market.get("markPrice")
            or live_market.get("price")
            or fill_price
            if live_market
            else fill_price
        )
        existing = next(
            (
                position
                for position in self.store.list_open_positions(order["walletId"])
                if position["orderId"] == order["id"]
            ),
            None,
        )
        if existing:
            previous_size = float(existing["size"])
            total_size = previous_size + filled_size
            weighted_entry = (
                previous_size * float(existing["entryPrice"]) + fill_notional
            ) / total_size
            armed_protection = bool(
                existing.get("exchangeStopOrderId")
                or existing.get("exchangeTakeProfitOrderId")
            )
            protection_misaligned = armed_protection and order["mode"] == "live"
            was_unprotected = existing.get("protectiveStatus") == "unprotected"
            trailing_watermark = existing.get("trailingWatermark")
            if not armed_protection:
                trailing_watermark = protective["trailingWatermark"]
                if existing.get("trailingWatermark") is not None:
                    if side == "Buy" and trailing_watermark is not None:
                        trailing_watermark = max(
                            float(existing["trailingWatermark"]),
                            float(trailing_watermark),
                        )
                    elif side == "Sell" and trailing_watermark is not None:
                        trailing_watermark = min(
                            float(existing["trailingWatermark"]),
                            float(trailing_watermark),
                        )
                    else:
                        trailing_watermark = existing["trailingWatermark"]
            recomputed_status = (
                "pending"
                if any(
                    position_level is not None
                    for position_level in (
                        protective["stopPrice"],
                        protective["takeProfitPrice"],
                        protective["trailingStopPct"],
                    )
                )
                else "disabled"
            )
            if order["mode"] == "live" and recomputed_status == "pending":
                recomputed_status = "unprotected"
            existing.update(
                {
                    "entryPrice": weighted_entry,
                    "markPrice": live_mark,
                    "size": total_size,
                    "notional": round(weighted_entry * total_size, 2),
                    "liquidationPrice": _liquidation_price(
                        weighted_entry,
                        order["leverage"],
                        side,
                    ),
                    "margin": round(
                        weighted_entry * total_size / order["leverage"],
                        2,
                    )
                    if order["leverage"]
                    else round(weighted_entry * total_size, 2),
                    "trailingWatermark": trailing_watermark,
                    "protectiveStatus": (
                        "unprotected" if protection_misaligned else recomputed_status
                    ),
                    "trailingUnsupported": order["mode"] == "live"
                    and float(risk_config.get("trailingStopPct") or 0.0) > 0,
                }
            )
            if not armed_protection:
                existing.update(
                    {
                        "stopPrice": protective["stopPrice"],
                        "takeProfitPrice": protective["takeProfitPrice"],
                        "trailingStopPct": protective["trailingStopPct"],
                    }
                )
            self.store.update_position(existing)
            if protection_misaligned and not was_unprotected:
                self.alert_engine.execution_divergence(
                    "Live protective triggers cover only part of the position and remain "
                    "priced off the original entry; manual re-arming is required.",
                    order["walletId"],
                    existing["id"],
                )
            return self._normalize_position_side(existing)

        _, position_id = self.store.generate_ids()
        position = {
            "id": position_id,
            "orderId": order["id"],
            "walletId": order["walletId"],
            "symbol": order["symbol"],
            "side": side,
            "mode": order["mode"],
            "entryPrice": fill_price,
            "markPrice": live_mark,
            "size": filled_size,
            "notional": round(fill_notional, 2),
            "leverage": order["leverage"],
            "pnl": 0.0,
            "pnlPct": 0.0,
            "liquidationPrice": _liquidation_price(fill_price, order["leverage"], side),
            "margin": round(fill_notional / order["leverage"], 2)
            if order["leverage"]
            else round(fill_notional, 2),
            "status": "open",
            **protective,
            "protectiveStatus": (
                "pending"
                if any(
                    position_level is not None
                    for position_level in (
                        protective["stopPrice"],
                        protective["takeProfitPrice"],
                        protective["trailingStopPct"],
                    )
                )
                else "disabled"
            ),
            "trailingUnsupported": order["mode"] == "live"
            and float(risk_config.get("trailingStopPct") or 0.0) > 0,
            "openedAt": datetime.now(timezone.utc).isoformat(),
            "closedAt": None,
        }
        self.store.create_position(position)
        if order["mode"] == "live" and exchange is not None:
            self._place_live_protection(position, exchange)
        elif order["mode"] == "live" and position["protectiveStatus"] == "pending":
            position["protectiveStatus"] = "unprotected"
            self.store.update_position(position)
            self.alert_engine.protective_unprotected(
                "Live protective triggers could not be signed from the refresh monitor.",
                order["walletId"],
                position["id"],
            )
        self.alert_engine.position_opened(position, order["walletId"])
        return self._normalize_position_side(position)

    def _paper_slippage(self, symbol: str, notional: float) -> tuple[float, str]:
        try:
            return float(self.client.estimate_slippage(symbol, notional)), "live_book"
        except Exception:  # noqa: BLE001
            return PAPER_SLIPPAGE, "fallback"

    def _lookup_fills(
        self,
        address: str,
        exchange_order_id: str | None,
    ) -> list[dict[str, Any]]:
        if exchange_order_id is None:
            return []
        for attempt in range(FILL_LOOKUP_ATTEMPTS):
            fills = self.client.get_user_fills(address, force=attempt > 0)
            matching = [
                fill for fill in fills
                if str(fill.get("oid") or fill.get("orderId") or "") == exchange_order_id
            ]
            if matching:
                return matching
            if attempt + 1 < FILL_LOOKUP_ATTEMPTS:
                time.sleep(FILL_LOOKUP_DELAY_SECONDS)
        return []

    def execute(
        self,
        signal_id: str,
        wallet_id: str,
        mode: Literal["paper", "live"] = "paper",
        master_password: str | None = None,
        order_type: Literal["market", "limit"] = "market",
        limit_price: float | None = None,
        tif: Literal["Alo", "Gtc", "Ioc"] = "Alo",
        expire_minutes: float | None = None,
    ) -> dict[str, Any]:
        if order_type not in {"market", "limit"}:
            raise ValueError(f"Unsupported orderType: {order_type}")
        if tif not in {"Alo", "Gtc", "Ioc"}:
            raise ValueError(f"Unsupported time-in-force: {tif}")
        signal = self.signal_store.get_signal(signal_id)
        if not signal:
            raise ValueError(f"Signal {signal_id} not found")
        if signal["action"] not in ("BUY", "SELL"):
            raise ValueError(f"Signal action is {signal['action']}; nothing to execute")

        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        if mode == "live":
            self._require_live_gates(wallet_id)

        symbol = signal["symbol"]
        market = self.client.get_market(symbol)
        if not market:
            raise ValueError(f"Market {symbol} not found")

        side = _side_for_signal(signal["action"])
        size_usd = signal["size"] or 0.0
        leverage = signal.get("leverage") or 1
        if mode == "live":
            max_leverage = max(1, int(market.get("maxLeverage") or leverage))
            leverage = min(int(leverage), max_leverage)
        entry = signal.get("entry") or market.get("price") or 0.0
        if order_type == "limit":
            derived_price, best_bid, best_ask = self._best_limit_price(symbol, side)
            limit_price = derived_price if limit_price is None else float(limit_price)
            self._validate_post_only_price(side, limit_price, best_bid, best_ask, tif)
            entry = limit_price
        size_coin = size_usd / entry if entry else 0.0
        notional = size_usd

        risk_config = signal.get("meta", {}).get("riskConfig") or {}
        try:
            self.portfolio_engine.can_open_position(
                wallet_id, symbol, notional, leverage, risk_config
            )
        except ValueError as exc:
            self.alert_engine.risk_violation(str(exc), wallet_id=wallet_id)
            raise

        order_id, _position_id = self.store.generate_ids()
        now = datetime.now(timezone.utc).isoformat()
        expires_at = self._expires_at(datetime.fromisoformat(now), expire_minutes)

        exchange = None
        exchange_order_id = None
        filled_size = 0.0
        if order_type == "limit":
            fill_price = float(limit_price)
            fees = 0.0
            order_status = "resting"
            meta = {
                "paper": mode == "paper",
                "live": mode == "live",
                "signal": signal,
                "orderType": "limit",
                "queueModelled": False,
                "paperMakerFillBasis": (
                    "fills when mark reaches limit; full fill, no queue model"
                    if mode == "paper"
                    else None
                ),
            }
            if mode == "live":
                if not master_password:
                    raise ValueError("masterPassword required for live execution")
                private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
                if not private_key:
                    raise ValueError("Could not decrypt wallet private key (wrong password?)")
                exchange = _live_exchange(wallet, private_key)
                _set_live_leverage(exchange, symbol, leverage)
                result = exchange.order(
                    symbol,
                    side == "Buy",
                    float(size_coin),
                    float(limit_price),
                    {"limit": {"tif": tif}},
                )
                meta["exchangeResult"] = result
                exchange_order_id = _exchange_order_id(result)
                meta["exchangeOrderId"] = exchange_order_id
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                status = statuses[0] if statuses else {}
                filled = status.get("filled") if isinstance(status, dict) else None
                if isinstance(filled, dict):
                    order_status = "filled"
                    fill_price = float(filled.get("avgPx") or fill_price)
                    filled_size = float(filled.get("totalSz") or size_coin)
                    fee_rate, fee_source = self._fee_rate(wallet.address)
                    fees = round(fill_price * filled_size * fee_rate, 4)
                    fills = self._lookup_fills(wallet.address, exchange_order_id)
                    if fills:
                        measured = _fill_metrics(fills)
                        fill_price = measured["price"] or fill_price
                        filled_size = measured["size"] or filled_size
                        fees = round(measured["fees"], 4)
                        meta.update(
                            {
                                "fills": fills,
                                "costSource": "exchange_fills",
                                "actualFee": fees,
                            }
                        )
                    else:
                        meta.update(
                            {
                                "costSource": "estimated",
                                "estimatedFee": fees,
                                "feeSource": fee_source,
                            }
                        )
                elif exchange_order_id is None:
                    order_status = "cancelled"
            else:
                meta["costSource"] = "paper_maker_pending"
        elif mode == "paper":
            slippage_pct, slippage_source = self._paper_slippage(symbol, notional)
            fill_price = _paper_fill(symbol, side, notional, self.client, slippage_pct)
            fee_rate, fee_source = self._fee_rate(wallet.address)
            fees = round(notional * fee_rate, 4)
            meta = {
                "paper": True,
                "signal": signal,
                "fillPrice": fill_price,
                "feeSource": fee_source,
                "slippageSource": slippage_source,
                "costSource": "paper_calibrated",
            }
            order_status = "filled"
            filled_size = size_coin
        else:
            if not master_password:
                raise ValueError("masterPassword required for live execution")
            private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
            if not private_key:
                raise ValueError("Could not decrypt wallet private key (wrong password?)")
            exchange = _live_exchange(wallet, private_key)
            _set_live_leverage(exchange, symbol, leverage)
            is_buy = side == "Buy"
            result = exchange.market_open(symbol, is_buy, float(size_coin), None, 0.01)
            meta = {"live": True, "signal": signal, "exchangeResult": result}
            order_status = "filled" if result.get("status") == "ok" else "failed"
            fill_price = entry
            fee_rate, fee_source = self._fee_rate(wallet.address)
            fees = round(notional * fee_rate, 4)
            if order_status == "filled":
                filled = result["response"]["data"]["statuses"][0].get("filled", {})
                fill_price = float(filled.get("avgPx") or fill_price)
                size_coin = float(filled.get("totalSz") or size_coin)
                notional = fill_price * size_coin
                exchange_order_id = _exchange_order_id(result)
                fills = self._lookup_fills(wallet.address, exchange_order_id)
                if fills:
                    measured = _fill_metrics(fills)
                    fill_price = measured["price"] or fill_price
                    size_coin = measured["size"] or size_coin
                    notional = fill_price * size_coin
                    fees = round(measured["fees"], 4)
                    meta.update(
                        {
                            "exchangeOrderId": exchange_order_id,
                            "fills": fills,
                            "costSource": "exchange_fills",
                            "actualFee": fees,
                        }
                    )
                else:
                    meta.update(
                        {
                            "exchangeOrderId": exchange_order_id,
                            "costSource": "estimated",
                            "estimatedFee": fees,
                            "feeSource": fee_source,
                        }
                    )
                filled_size = size_coin
                exchange_order_id = meta.get("exchangeOrderId")

        order = {
            "id": order_id,
            "signalId": signal_id,
            "walletId": wallet_id,
            "symbol": symbol,
            "side": side,
            "size": size_coin,
            "price": fill_price,
            "notional": round(notional, 2),
            "leverage": leverage,
            "fees": fees,
            "type": "Limit" if order_type == "limit" else "Market",
            "mode": mode,
            "status": order_status,
            "timestamp": now,
            "meta": meta,
            "limitPrice": limit_price if order_type == "limit" else None,
            "tif": tif if order_type == "limit" else None,
            "filledSize": filled_size,
            "expiresAt": expires_at,
            "exchangeOrderId": exchange_order_id,
            "updatedAt": now,
        }
        if order_status == "filled" and order["filledSize"] <= 0:
            order["filledSize"] = order["size"]
        self.store.create_order(order)

        if order_status != "filled":
            return {"order": order, "position": None}

        position = self._create_position_from_fill(
            order,
            fill_price,
            filled_size,
            wallet,
            risk_config,
            exchange,
        )
        return {"order": self.store.get_order(order_id) or order, "position": position}

    def close_position(
        self,
        position_id: str,
        wallet_id: str,
        mode: Literal["paper", "live"] = "paper",
        master_password: str | None = None,
        exit_reason: str = "signal",
        theoretical_trigger_price: float | None = None,
        _bypass_live_gate: bool = False,
        _exchange: Any | None = None,
        _cancel_protection: bool = True,
    ) -> dict[str, Any]:
        position = self.store.get_position(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position["status"] != "open":
            raise ValueError(f"Position {position_id} is already {position['status']}")

        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        if mode == "live" and not _bypass_live_gate:
            self._require_live_gates(wallet_id)

        symbol = position["symbol"]
        side = position["side"]
        size_coin = position["size"]
        entry = position["entryPrice"]

        order = self.store.get_order(position["orderId"])
        order_meta = (order or {}).get("meta") or {}
        if mode != position.get("mode", mode):
            raise ValueError("Requested execution mode does not match the position mode")

        exchange = _exchange
        if mode == "paper":
            slippage_pct, _slippage_source = self._paper_slippage(symbol, position["notional"])
            exit_price = _paper_fill(
                symbol,
                "Sell" if side == "Buy" else "Buy",
                position["notional"],
                self.client,
                slippage_pct,
            )
        else:
            if not master_password:
                raise ValueError("masterPassword required for live close")
            private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
            if not private_key:
                raise ValueError("Could not decrypt wallet private key")
            exchange = exchange or _live_exchange(wallet, private_key)
            if _cancel_protection:
                self._cancel_live_protection(position, exchange)
            result = exchange.market_close(symbol, float(size_coin))
            exit_price = entry  # fallback
            if result.get("status") == "ok":
                filled = result["response"]["data"]["statuses"][0].get("filled", {})
                exit_price = float(filled.get("avgPx") or exit_price)
            else:
                raise RuntimeError(f"Live close failed: {result}")

        if side == "Buy":
            gross = size_coin * (exit_price - entry)
        else:
            gross = size_coin * (entry - exit_price)
        fee_rate, _fee_source = self._fee_rate(wallet.address)
        fees = position["notional"] * fee_rate * 2  # open + close
        funding_paid = 0.0
        funding_rows: list[dict[str, Any]] = []
        cost_source = "estimated"
        exchange_closed_pnl: float | None = None
        close_fills: list[dict[str, Any]] = []
        if mode == "live":
            close_order_id = _exchange_order_id(result)
            close_fills = self._lookup_fills(wallet.address, close_order_id)
            if close_fills:
                measured = _fill_metrics(close_fills)
                exit_price = measured["price"] or exit_price
                close_fee = measured["fees"]
                entry_fee = float(order_meta.get("actualFee") or order_meta.get("estimatedFee") or 0.0)
                fees = entry_fee + close_fee
                exchange_closed_pnl = measured["closedPnl"]
                try:
                    funding_paid, funding_rows = _funding_paid(
                        self.client,
                        wallet.address,
                        symbol,
                        position["openedAt"],
                        datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:  # noqa: BLE001
                    funding_paid = 0.0
                # This assumes Hyperliquid closedPnl is gross of fees; verify against the UI.
                net_pnl = exchange_closed_pnl - fees - funding_paid
                cost_source = "exchange_fills"
            else:
                net_pnl = gross - fees
        else:
            net_pnl = gross - fees
        pnl_pct = (net_pnl / position["notional"] * 100) if position["notional"] else 0.0

        now = datetime.now(timezone.utc).isoformat()
        position["markPrice"] = exit_price
        position["pnl"] = round(net_pnl, 4)
        position["pnlPct"] = round(pnl_pct, 4)
        position["status"] = "closed"
        position["exitReason"] = exit_reason
        position["protectiveStatus"] = "triggered" if exit_reason != "signal" else "closed"
        position["exchangeStopOrderId"] = None
        position["exchangeTakeProfitOrderId"] = None
        position["closedAt"] = now
        self.store.update_position(position)

        if order:
            order["status"] = "closed"
            order["meta"] = order.get("meta") or {}
            order["meta"]["closePrice"] = exit_price
            order["meta"]["netPnl"] = net_pnl
            order["meta"]["internalNetPnl"] = gross - fees
            order["meta"]["costSource"] = cost_source
            order["meta"]["exitReason"] = exit_reason
            if theoretical_trigger_price is not None:
                order["meta"]["protectiveTriggerPrice"] = theoretical_trigger_price
                order["meta"]["protectiveFillPrice"] = exit_price
            if mode == "live":
                order["meta"]["closeFills"] = close_fills
                order["meta"]["actualFee"] = fees
                order["meta"]["fundingPaid"] = funding_paid
                order["meta"]["fundingRecords"] = funding_rows
                order["meta"]["exchangeClosedPnl"] = exchange_closed_pnl
                order["meta"]["netPnlBasis"] = "exchangeClosedPnl - fees - funding"
            self.store.update_order(order)

        if mode == "live" and exchange_closed_pnl is not None:
            internal_net_pnl = gross - fees
            tolerance = max(PNL_DIVERGENCE_TOLERANCE, abs(internal_net_pnl) * 0.001)
            if abs(net_pnl - internal_net_pnl) > tolerance:
                self.alert_engine.execution_divergence(
                    f"Exchange-derived PnL ${net_pnl:.4f} differs from internal estimate "
                    f"${internal_net_pnl:.4f} by ${abs(net_pnl - internal_net_pnl):.4f}.",
                    wallet_id,
                    position["id"],
                )
        if mode == "paper":
            self.portfolio_engine.release_pnl(wallet_id, net_pnl, mode=mode)
        self.alert_engine.position_closed(position, net_pnl, wallet_id)
        self.alert_engine.journal_closed_trade(position, order, net_pnl, gross, fees, wallet_id)

        return {"position": self._normalize_position_side(position), "netPnl": round(net_pnl, 4)}

    def _place_live_protection(self, position: dict[str, Any], exchange: Any) -> None:
        """Place reduce-only market triggers after a live entry fill."""
        close_is_buy = position["side"] == "Sell"
        placed: dict[str, str | None] = {
            "exchangeStopOrderId": None,
            "exchangeTakeProfitOrderId": None,
        }
        try:
            for field, price, tpsl in (
                ("exchangeStopOrderId", position.get("stopPrice"), "sl"),
                ("exchangeTakeProfitOrderId", position.get("takeProfitPrice"), "tp"),
            ):
                if price is None:
                    continue
                limit_price = (
                    float(price) * (1 + TRIGGER_SLIPPAGE)
                    if close_is_buy
                    else float(price) * (1 - TRIGGER_SLIPPAGE)
                )
                result = exchange.order(
                    position["symbol"],
                    close_is_buy,
                    float(position["size"]),
                    limit_price,
                    {
                        "trigger": {
                            "triggerPx": float(price),
                            "isMarket": True,
                            "tpsl": tpsl,
                        }
                    },
                    reduce_only=True,
                )
                order_id = _exchange_order_id(result)
                if order_id is None:
                    raise ValueError(f"Exchange did not return a trigger order id for {tpsl}")
                placed[field] = order_id
            position.update(placed)
            position["protectiveStatus"] = "armed"
            self.store.update_position(position)
            if position.get("trailingUnsupported"):
                self.alert_engine.protective_unsupported(
                    position,
                    position["walletId"],
                )
        except Exception as exc:  # noqa: BLE001
            position.update(placed)
            position["protectiveStatus"] = "unprotected"
            self.store.update_position(position)
            self.alert_engine.protective_unprotected(
                f"Could not place live protective triggers: {exc}",
                position["walletId"],
                position["id"],
            )

    def _cancel_live_protection(self, position: dict[str, Any], exchange: Any) -> None:
        """Best-effort cancellation of resting protective triggers."""
        for order_id in (
            position.get("exchangeStopOrderId"),
            position.get("exchangeTakeProfitOrderId"),
        ):
            if not order_id:
                continue
            try:
                exchange.cancel(position["symbol"], int(order_id))
            except Exception as exc:  # noqa: BLE001
                self.alert_engine.protective_unprotected(
                    f"Could not cancel protective trigger {order_id}: {exc}",
                    position["walletId"],
                    position["id"],
                )

    def _monitor_paper_protection(self, position: dict[str, Any]) -> None:
        if position.get("protectiveStatus") == "disabled":
            return
        if position.get("protectiveStatus") == "pending":
            position["protectiveStatus"] = "armed"
            self.store.update_position(position)
            return
        if position.get("protectiveStatus") != "armed":
            return
        evaluation = evaluate_protective_exit(position, position["markPrice"])
        position["trailingWatermark"] = evaluation["watermark"]
        if evaluation["reason"] is None:
            self.store.update_position(position)
            return
        position["protectiveStatus"] = "triggered"
        self.store.update_position(position)
        self.alert_engine.protective_triggered(
            position,
            evaluation["reason"],
            float(evaluation["triggerPrice"]),
            position["walletId"],
        )
        self.close_position(
            position["id"],
            position["walletId"],
            mode="paper",
            exit_reason=evaluation["reason"],
            theoretical_trigger_price=evaluation["triggerPrice"],
        )

    def _settle_pending_fill(
        self,
        order: dict[str, Any],
        wallet: Wallet,
        fill_price: float,
        filled_size: float,
        fees: float,
        risk_config: dict[str, Any],
        exchange: Any | None = None,
    ) -> dict[str, Any]:
        order["filledSize"] = float(order.get("filledSize") or 0.0) + filled_size
        order["fees"] = round(float(order.get("fees") or 0.0) + fees, 4)
        order["price"] = fill_price
        requested_size = float(order["size"])
        order["status"] = (
            "filled"
            if order["filledSize"] >= requested_size - 1e-9
            else "partially_filled"
        )
        order["meta"] = order.get("meta") or {}
        order["meta"]["actualFee"] = order["fees"]
        self.store.update_order(order)
        return self._create_position_from_fill(
            order,
            fill_price,
            filled_size,
            wallet,
            risk_config,
            exchange,
        )

    def _monitor_pending_orders(self) -> None:
        """Advance paper and live resting orders without signing transactions."""
        now = datetime.now(timezone.utc)
        live_orders_by_wallet: dict[str, list[dict[str, Any]]] = {}
        for order in self.store.list_pending_orders():
            expires_at = order.get("expiresAt")
            if expires_at:
                try:
                    expired = now >= datetime.fromisoformat(expires_at)
                except ValueError:
                    expired = False
                if expired and order["mode"] == "paper":
                    order["status"] = "expired"
                    self.store.update_order(order)
                    self.alert_engine.execution_divergence(
                        f"Paper limit order {order['id']} expired before filling.",
                        order["walletId"],
                        order["id"],
                    )
                    continue
                if expired and order["mode"] == "live":
                    order["meta"] = order.get("meta") or {}
                    if not order["meta"].get("expiryWarned"):
                        order["meta"]["expiryWarned"] = True
                        self.store.update_order(order)
                        self.alert_engine.execution_divergence(
                            f"Live limit order {order['id']} passed its expiry; manual cancellation is required.",
                            order["walletId"],
                            order["id"],
                        )

            wallet = self.wallet_store.get_wallet(order["walletId"])
            if not wallet:
                continue
            risk_config = (
                (order.get("meta") or {}).get("signal", {}).get("meta", {}).get("riskConfig")
                or {}
            )
            if order["mode"] == "paper":
                market = self.client.get_market(order["symbol"])
                mark = (
                    (market.get("markPrice") or market.get("price"))
                    if market
                    else None
                )
                limit_price = order.get("limitPrice")
                if (
                    mark is None
                    or limit_price is None
                    or (
                        order["side"] == "Buy"
                        and float(mark) > float(limit_price)
                    )
                    or (
                        order["side"] == "Sell"
                        and float(mark) < float(limit_price)
                    )
                ):
                    continue
                fee_rate, fee_source = self._maker_fee_rate(wallet.address)
                remaining_size = max(
                    0.0,
                    float(order["size"]) - float(order.get("filledSize") or 0.0),
                )
                if not remaining_size:
                    continue
                fees = round(float(limit_price) * remaining_size * fee_rate, 4)
                order["meta"] = order.get("meta") or {}
                order["meta"]["feeSource"] = fee_source
                order["meta"]["costSource"] = "paper_maker"
                self._settle_pending_fill(
                    order,
                    wallet,
                    float(limit_price),
                    remaining_size,
                    fees,
                    risk_config,
                )
                continue
            live_orders_by_wallet.setdefault(order["walletId"], []).append(order)

        for wallet_id, orders in live_orders_by_wallet.items():
            wallet = self.wallet_store.get_wallet(wallet_id)
            if not wallet:
                continue
            try:
                exchange_orders = self.client.get_open_orders(wallet.address, force=True)
                user_fills = self.client.get_user_fills(wallet.address, force=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Live pending-order check failed for wallet %s: %s", wallet_id, exc)
                continue
            resting = {
                str(item.get("oid") or item.get("orderId"))
                for item in exchange_orders
            }
            for order in orders:
                risk_config = (
                    (order.get("meta") or {}).get("signal", {}).get("meta", {}).get("riskConfig")
                    or {}
                )
                exchange_order_id = order.get("exchangeOrderId")
                matched_fills = [
                    fill
                    for fill in user_fills
                    if exchange_order_id is not None
                    and str(fill.get("oid") or fill.get("orderId")) == str(exchange_order_id)
                ]
                measured = (
                    _fill_metrics(matched_fills)
                    if matched_fills
                    else {"size": 0.0, "price": 0.0, "fees": 0.0}
                )
                observed_size = float(measured["size"])
                current_size = float(order.get("filledSize") or 0.0)
                new_size = observed_size - current_size
                if new_size > 1e-9:
                    previous_fees = float((order.get("meta") or {}).get("measuredFees") or 0.0)
                    new_fees = max(0.0, float(measured["fees"]) - previous_fees)
                    order["meta"] = order.get("meta") or {}
                    order["meta"]["measuredFees"] = float(measured["fees"])
                    self._settle_pending_fill(
                        order,
                        wallet,
                        float(measured["price"] or order["price"]),
                        new_size,
                        new_fees,
                        risk_config,
                    )
                    current_size = observed_size
                if current_size >= float(order["size"]) - 1e-9:
                    order["status"] = "filled"
                    self.store.update_order(order)
                elif exchange_order_id is not None and str(exchange_order_id) in resting:
                    order["status"] = "partially_filled" if current_size else "resting"
                    self.store.update_order(order)
                else:
                    order["status"] = "cancelled"
                    self.store.update_order(order)
                    self.alert_engine.execution_divergence(
                        f"Live limit order {order['id']} disappeared from exchange with "
                        f"{current_size:.8f} of {order['size']:.8f} filled; no unobserved fill assumed.",
                        order["walletId"],
                        order["id"],
                    )

    def _monitor_live_protection(self, position: dict[str, Any]) -> None:
        expected = {
            str(order_id)
            for order_id in (
                position.get("exchangeStopOrderId"),
                position.get("exchangeTakeProfitOrderId"),
            )
            if order_id
        }
        if not expected or position.get("protectiveStatus") == "unprotected":
            return
        wallet = self.wallet_store.get_wallet(position["walletId"])
        if not wallet:
            return
        try:
            resting = self.client.get_open_orders(wallet.address)
            present = {
                str(order.get("oid") or order.get("orderId"))
                for order in resting
            }
            missing = expected - present
            if missing:
                state = self.client.get_clearinghouse_state(wallet.address, force=True)
                exchange_position = next(
                    (
                        asset.get("position", {})
                        for asset in state.get("assetPositions", [])
                        if str(asset.get("position", {}).get("coin", "")).upper()
                        == position["symbol"].upper()
                        and abs(float(asset.get("position", {}).get("szi") or 0.0)) > 1e-9
                    ),
                    None,
                )
                if exchange_position is None:
                    logger.warning(
                        "Live trigger %s vanished after exchange position %s closed; "
                        "reconciliation will report any local divergence.",
                        sorted(missing),
                        position["symbol"],
                    )
                else:
                    position["protectiveStatus"] = "unprotected"
                    self.store.update_position(position)
                    self.alert_engine.protective_unprotected(
                        f"Expected live protective orders are missing: {sorted(missing)}",
                        position["walletId"],
                        position["id"],
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live protective order check failed for %s: %s", position["symbol"], exc)

    def list_exchange_orders(self, wallet_id: str) -> list[dict[str, Any]]:
        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")
        return self.client.get_open_orders(wallet.address, force=True)

    def cancel_exchange_order(
        self,
        wallet_id: str,
        symbol: str,
        order_id: str,
        master_password: str | None = None,
    ) -> dict[str, Any]:
        local = self.store.get_order(order_id)
        if local and local["walletId"] == wallet_id and local["mode"] == "paper":
            if local["status"] not in {"resting", "partially_filled"}:
                raise ValueError(f"Order {order_id} is already {local['status']}")
            local["status"] = "cancelled"
            self.store.update_order(local)
            return {
                "walletId": wallet_id,
                "symbol": local["symbol"],
                "orderId": order_id,
                "status": "cancelled",
                "result": None,
            }
        self._require_live_gates(wallet_id)
        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")
        if not master_password:
            raise ValueError("masterPassword required for live order cancellation")
        private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
        if not private_key:
            raise ValueError("Could not decrypt wallet private key")
        exchange = _live_exchange(wallet, private_key)
        exchange_order_id = (
            str(local.get("exchangeOrderId"))
            if local and local["walletId"] == wallet_id and local.get("exchangeOrderId")
            else order_id
        )
        result = exchange.cancel(symbol, int(exchange_order_id))
        self.client.get_open_orders(wallet.address, force=True)
        local = self.store.get_order_by_exchange_id(wallet_id, exchange_order_id)
        if local and local["status"] in {"resting", "partially_filled"}:
            local["status"] = "cancelled"
            self.store.update_order(local)
        return {
            "walletId": wallet_id,
            "symbol": symbol,
            "orderId": exchange_order_id,
            "localOrderId": local["id"] if local else None,
            "result": result,
        }

    def kill_switch(
        self,
        wallet_id: str,
        mode: Literal["paper", "live"],
        master_password: str | None = None,
    ) -> dict[str, Any]:
        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")
        self.portfolio_engine.portfolio_store.set_live_enabled(wallet_id, False)
        exchange = None
        order_results: list[dict[str, Any]] = []
        if mode == "live":
            if not master_password:
                raise ValueError("masterPassword required for live kill switch")
            private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
            if not private_key:
                raise ValueError("Could not decrypt wallet private key")
            exchange = _live_exchange(wallet, private_key)
            try:
                resting = self.client.get_open_orders(wallet.address, force=True)
            except Exception as exc:  # noqa: BLE001
                resting = []
                order_results.append({"status": "error", "error": str(exc)})
            for order in resting:
                symbol = str(order.get("coin") or order.get("symbol") or "")
                order_id = order.get("oid") or order.get("orderId")
                outcome: dict[str, Any] = {
                    "symbol": symbol,
                    "orderId": str(order_id),
                }
                try:
                    outcome["result"] = exchange.cancel(symbol, int(order_id))
                    outcome["status"] = "cancelled"
                except Exception as exc:  # noqa: BLE001
                    outcome["status"] = "error"
                    outcome["error"] = str(exc)
                order_results.append(outcome)
            for local in self.store.list_pending_orders(wallet_id, mode="live"):
                if local["status"] not in {"resting", "partially_filled"}:
                    continue
                local["status"] = "cancelled"
                self.store.update_order(local)
                order_results.append(
                    {
                        "symbol": local["symbol"],
                        "orderId": local.get("exchangeOrderId") or local["id"],
                        "localOrderId": local["id"],
                        "status": "cancelled",
                    }
                )
        else:
            for local in self.store.list_pending_orders(wallet_id, mode="paper"):
                local["status"] = "cancelled"
                self.store.update_order(local)
                order_results.append(
                    {
                        "symbol": local["symbol"],
                        "orderId": local["id"],
                        "status": "cancelled",
                    }
                )

        position_results: list[dict[str, Any]] = []
        positions = [
            position
            for position in self.store.list_open_positions(wallet_id)
            if position.get("mode", "paper") == mode
        ]
        for position in positions:
            outcome = {"positionId": position["id"]}
            try:
                outcome.update(
                    self.close_position(
                        position["id"],
                        wallet_id,
                        mode=mode,
                        master_password=master_password,
                        _bypass_live_gate=mode == "live",
                        _exchange=exchange,
                        _cancel_protection=mode != "live",
                    )
                )
                outcome["status"] = "closed"
            except Exception as exc:  # noqa: BLE001
                outcome["status"] = "error"
                outcome["error"] = str(exc)
            position_results.append(outcome)

        self.alert_engine.kill_switch(wallet_id, mode)
        return {
            "walletId": wallet_id,
            "mode": mode,
            "orders": order_results,
            "positions": position_results,
            "liveEnabled": False,
        }

    def _require_live_gates(self, wallet_id: str) -> None:
        if not is_live_trading_enabled():
            raise ValueError("Global live trading gate is off. Set LIVE_TRADING=true to enable.")
        if not self.portfolio_engine.portfolio_store.is_live_enabled(wallet_id):
            raise ValueError(
                f"Wallet live trading gate is off for {wallet_id}. "
                "Enable live trading for this wallet first."
            )

    @staticmethod
    def _normalize_position_side(position: dict[str, Any]) -> dict[str, Any]:
        """Convert internal 'Buy'/'Sell' side to LONG/SHORT for the frontend."""
        position["side"] = "LONG" if position["side"] == "Buy" else "SHORT"
        return position

    def _compute_live_pnl(self, pos: dict[str, Any]) -> None:
        if pos.get("mode", "paper") == "live":
            wallet = self.wallet_store.get_wallet(pos["walletId"])
            if wallet:
                try:
                    state = self.client.get_clearinghouse_state(wallet.address)
                    for item in state.get("assetPositions", []):
                        exchange_position = item.get("position", item)
                        if str(exchange_position.get("coin", "")).upper() != pos["symbol"].upper():
                            continue
                        size = float(exchange_position.get("szi") or 0.0)
                        if not size:
                            break
                        position_value = float(exchange_position.get("positionValue") or 0.0)
                        if position_value:
                            pos["markPrice"] = abs(position_value / size)
                        pos["pnl"] = round(float(exchange_position.get("unrealizedPnl") or 0.0), 4)
                        pos["pnlSource"] = "exchange"
                        pos["pnlPct"] = round(
                            (pos["pnl"] / pos["notional"] * 100) if pos["notional"] else 0.0,
                            4,
                        )
                        return
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Exchange unrealized PnL lookup failed for %s: %s",
                        pos["symbol"],
                        exc,
                    )
        market = self.client.get_market(pos["symbol"])
        if not market:
            pos["pnlSource"] = "mark_price"
            return
        pos["pnlSource"] = "mark_price"
        mark = market.get("markPrice") or market.get("price") or pos["entryPrice"]
        pos["markPrice"] = mark
        if pos["side"] == "Buy":
            gross = pos["size"] * (mark - pos["entryPrice"])
        else:
            gross = pos["size"] * (pos["entryPrice"] - mark)
        pos["pnl"] = round(gross, 4)
        pos["pnlPct"] = round(
            (gross / pos["notional"] * 100) if pos["notional"] else 0.0, 4
        )

    def refresh_positions(self) -> None:
        """Update stored mark prices and unrealized PnL for all open positions."""
        self._monitor_pending_orders()
        positions = self.store.list_open_positions()
        for pos in positions:
            self._compute_live_pnl(pos)
            self.store.mark_position_price(
                pos["id"], pos["markPrice"], pos["pnl"], pos["pnlPct"]
            )
            if pos.get("mode", "paper") == "paper":
                self._monitor_paper_protection(pos)
            else:
                self._monitor_live_protection(pos)

    def list_positions(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        positions = self.store.list_positions(wallet_id)
        # Re-mark open positions to current price for unrealized PnL.
        for pos in positions:
            if pos["status"] == "open":
                self._compute_live_pnl(pos)
            else:
                pos["pnlSource"] = "mark_price"
            pos["side"] = "LONG" if pos["side"] == "Buy" else "SHORT"
        return positions

    def list_orders(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_orders(wallet_id)
