"""Trade execution engine for Hyperliquid (paper and live modes)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from backend.models.wallet import Wallet
from backend.services.execution_store import ExecutionStore
from backend.services.hyperliquid_client import HyperliquidClient
from backend.services.signal_store import SignalStore
from backend.services.wallet_store import WalletStore

# Hyperliquid taker fee at base tier.
TAKER_FEE = 0.00045


def _side_for_signal(action: str) -> str:
    return "Buy" if action == "BUY" else "Sell" if action == "SELL" else "Hold"


def _liquidation_price(entry: float, leverage: int, side: str) -> float | None:
    if leverage <= 1 or entry <= 0:
        return None
    maintenance_margin = 0.01  # rough approximation
    if side == "Buy":
        return entry * (1 - (1 / leverage) + maintenance_margin)
    return entry * (1 + (1 / leverage) - maintenance_margin)


def _paper_fill(symbol: str, side: str) -> float:
    """Return a simulated fill price (slightly worse than mid)."""
    client = HyperliquidClient()
    market = client.get_market(symbol)
    price = market.get("price") or 0.0 if market else 0.0
    if not price:
        book = client.get_orderbook(symbol, levels=1)
        bids = book.get("bid", {})
        asks = book.get("ask", {})
        price = (
            (asks.get("avgPrice") or price) if side == "Buy" else (bids.get("avgPrice") or price)
        )
    # Add a tiny paper slippage.
    slippage = 0.0005
    multiplier = 1 + slippage if side == "Buy" else 1 - slippage
    return round(float(price) * multiplier, 8)


def _live_exchange(wallet: Wallet, private_key: str, testnet: bool = True):
    """Build a Hyperliquid ``Exchange`` client from a decrypted private key."""
    import eth_account  # noqa: F401
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants

    account = eth_account.Account.from_key(private_key)
    base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
    return Exchange(account, base_url, account_address=wallet.address)


class ExecutionEngine:
    """Execute persisted signals against Hyperliquid (paper or live)."""

    def __init__(self) -> None:
        self.store = ExecutionStore()
        self.signal_store = SignalStore()
        self.wallet_store = WalletStore()
        self.client = HyperliquidClient()

    def execute(
        self,
        signal_id: str,
        wallet_id: str,
        mode: Literal["paper", "live"] = "paper",
        master_password: str | None = None,
        testnet: bool = True,
    ) -> dict[str, Any]:
        signal = self.signal_store.get_signal(signal_id)
        if not signal:
            raise ValueError(f"Signal {signal_id} not found")
        if signal["action"] not in ("BUY", "SELL"):
            raise ValueError(f"Signal action is {signal['action']}; nothing to execute")

        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        symbol = signal["symbol"]
        market = self.client.get_market(symbol)
        if not market:
            raise ValueError(f"Market {symbol} not found")

        side = _side_for_signal(signal["action"])
        size_usd = signal["size"] or 0.0
        leverage = signal.get("leverage") or 1
        entry = signal.get("entry") or market.get("price") or 0.0
        size_coin = size_usd / entry if entry else 0.0
        notional = size_usd

        order_id, position_id = self.store.generate_ids()
        now = datetime.now(timezone.utc).isoformat()

        if mode == "paper":
            fill_price = _paper_fill(symbol, side)
            fees = round(notional * TAKER_FEE, 4)
            meta = {"paper": True, "signal": signal, "fillPrice": fill_price}
            order_status = "filled"
        else:
            if not master_password:
                raise ValueError("masterPassword required for live execution")
            private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
            if not private_key:
                raise ValueError("Could not decrypt wallet private key (wrong password?)")
            exchange = _live_exchange(wallet, private_key, testnet=testnet)
            is_buy = side == "Buy"
            result = exchange.market_open(symbol, is_buy, float(size_coin), None, 0.01)
            meta = {"live": True, "signal": signal, "exchangeResult": result}
            order_status = "filled" if result.get("status") == "ok" else "failed"
            fill_price = entry
            if order_status == "filled":
                filled = result["response"]["data"]["statuses"][0].get("filled", {})
                fill_price = float(filled.get("avgPx") or fill_price)
                size_coin = float(filled.get("totalSz") or size_coin)
                notional = fill_price * size_coin
            fees = round(notional * TAKER_FEE, 4)

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
        position = {
            "id": position_id,
            "orderId": order_id,
            "walletId": wallet_id,
            "symbol": symbol,
            "side": side,
            "entryPrice": fill_price,
            "markPrice": fill_price,
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
        return {"order": order, "position": self._normalize_position_side(position)}

    def close_position(
        self,
        position_id: str,
        wallet_id: str,
        mode: Literal["paper", "live"] = "paper",
        master_password: str | None = None,
        testnet: bool = True,
    ) -> dict[str, Any]:
        position = self.store.get_position(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position["status"] != "open":
            raise ValueError(f"Position {position_id} is already {position['status']}")

        wallet = self.wallet_store.get_wallet(wallet_id)
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        symbol = position["symbol"]
        side = position["side"]
        size_coin = position["size"]
        entry = position["entryPrice"]

        if mode == "paper":
            exit_price = _paper_fill(symbol, "Sell" if side == "Buy" else "Buy")
        else:
            if not master_password:
                raise ValueError("masterPassword required for live close")
            private_key = self.wallet_store.decrypt_private_key(wallet_id, master_password)
            if not private_key:
                raise ValueError("Could not decrypt wallet private key")
            exchange = _live_exchange(wallet, private_key, testnet=testnet)
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
        fees = position["notional"] * TAKER_FEE * 2  # open + close
        net_pnl = gross - fees
        pnl_pct = (net_pnl / position["notional"] * 100) if position["notional"] else 0.0

        now = datetime.now(timezone.utc).isoformat()
        position["markPrice"] = exit_price
        position["pnl"] = round(net_pnl, 4)
        position["pnlPct"] = round(pnl_pct, 4)
        position["status"] = "closed"
        position["closedAt"] = now
        self.store.update_position(position)

        order = self.store.get_order(position["orderId"])
        if order:
            order["status"] = "closed"
            order["meta"] = order.get("meta") or {}
            order["meta"]["closePrice"] = exit_price
            order["meta"]["netPnl"] = net_pnl
            self.store.update_order(order)

        return {"position": self._normalize_position_side(position), "netPnl": round(net_pnl, 4)}

    @staticmethod
    def _normalize_position_side(position: dict[str, Any]) -> dict[str, Any]:
        """Convert internal 'Buy'/'Sell' side to LONG/SHORT for the frontend."""
        position["side"] = "LONG" if position["side"] == "Buy" else "SHORT"
        return position

    def list_positions(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        positions = self.store.list_positions(wallet_id)
        # Re-mark open positions to current price for unrealized PnL.
        for pos in positions:
            if pos["status"] == "open":
                market = self.client.get_market(pos["symbol"])
                if market:
                    mark = market.get("price") or pos["entryPrice"]
                    pos["markPrice"] = mark
                    if pos["side"] == "Buy":
                        gross = pos["size"] * (mark - pos["entryPrice"])
                    else:
                        gross = pos["size"] * (pos["entryPrice"] - mark)
                    pos["pnl"] = round(gross, 4)
                    pos["pnlPct"] = round(
                        (gross / pos["notional"] * 100) if pos["notional"] else 0.0, 4
                    )
            pos["side"] = "LONG" if pos["side"] == "Buy" else "SHORT"
        return positions

    def list_orders(self, wallet_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_orders(wallet_id)
