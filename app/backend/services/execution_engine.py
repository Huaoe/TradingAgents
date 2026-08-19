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
from backend.services.signal_store import SignalStore
from backend.services.wallet_store import WalletStore

# Hyperliquid taker fee at base tier.
TAKER_FEE = 0.00045
PAPER_SLIPPAGE = 0.0005
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
            "openedAt": now,
            "closedAt": None,
        }
        self.store.create_position(position)
        self.alert_engine.position_opened(position, wallet_id)
        return {"order": order, "position": self._normalize_position_side(position)}

    def close_position(
        self,
        position_id: str,
        wallet_id: str,
        mode: Literal["paper", "live"] = "paper",
        master_password: str | None = None,
    ) -> dict[str, Any]:
        position = self.store.get_position(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position["status"] != "open":
            raise ValueError(f"Position {position_id} is already {position['status']}")

        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        if mode == "live":
            self._require_live_gates(wallet_id)

        symbol = position["symbol"]
        side = position["side"]
        size_coin = position["size"]
        entry = position["entryPrice"]

        order = self.store.get_order(position["orderId"])
        order_meta = (order or {}).get("meta") or {}
        if mode != position.get("mode", mode):
            raise ValueError("Requested execution mode does not match the position mode")

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
            exchange = _live_exchange(wallet, private_key)
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
        position["closedAt"] = now
        self.store.update_position(position)

        if order:
            order["status"] = "closed"
            order["meta"] = order.get("meta") or {}
            order["meta"]["closePrice"] = exit_price
            order["meta"]["netPnl"] = net_pnl
            order["meta"]["internalNetPnl"] = gross - fees
            order["meta"]["costSource"] = cost_source
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
