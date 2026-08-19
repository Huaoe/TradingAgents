"""Trade execution engine for Hyperliquid (paper and live modes)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
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
    ) -> dict[str, Any]:
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

        order_id, position_id = self.store.generate_ids()
        now = datetime.now(timezone.utc).isoformat()

        exchange = None
        if mode == "paper":
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
            "type": "Market",
            "mode": mode,
            "status": order_status,
            "timestamp": now,
            "meta": meta,
        }
        self.store.create_order(order)

        if order_status != "filled":
            return {"order": order, "position": None}

        liq = _liquidation_price(fill_price, leverage, side)
        margin = round(notional / leverage, 2) if leverage else round(notional, 2)
        live_market = self.client.get_market(symbol)
        live_mark = (
            live_market.get("markPrice")
            or live_market.get("price")
            or fill_price
            if live_market
            else fill_price
        )
        protective = protective_levels(fill_price, side, risk_config)
        position = {
            "id": position_id,
            "orderId": order_id,
            "walletId": wallet_id,
            "symbol": symbol,
            "side": side,
            "mode": mode,
            "entryPrice": fill_price,
            "markPrice": live_mark,
            "size": size_coin,
            "notional": round(notional, 2),
            "leverage": leverage,
            "pnl": 0.0,
            "pnlPct": 0.0,
            "liquidationPrice": liq,
            "margin": margin,
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
            "trailingUnsupported": mode == "live"
            and float(risk_config.get("trailingStopPct") or 0.0) > 0,
            "openedAt": now,
            "closedAt": None,
        }
        self.store.create_position(position)
        if mode == "live" and exchange is not None:
            self._place_live_protection(position, exchange)
        self.alert_engine.position_opened(position, wallet_id)
        return {"order": order, "position": self._normalize_position_side(position)}

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
        master_password: str,
    ) -> dict[str, Any]:
        self._require_live_gates(wallet_id)
        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")
        private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
        if not private_key:
            raise ValueError("Could not decrypt wallet private key")
        exchange = _live_exchange(wallet, private_key)
        result = exchange.cancel(symbol, int(order_id))
        self.client.get_open_orders(wallet.address, force=True)
        return {"walletId": wallet_id, "symbol": symbol, "orderId": order_id, "result": result}

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
