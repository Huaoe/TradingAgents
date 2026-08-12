# Agent Strategy Design — Hyperliquid Trading Bot

**Repo:** `Huaoe/TradingAgents` (upstream `TradingAgents` v0.3.1)  
**Date:** 2026-08-12  
**Scope:** Define the multi-agent configuration, prompts, signal-to-order mapping, risk guardrails, backtest simulation, and implementation order for the personal Hyperliquid trading app.

---

## 1. Philosophy

The bot should be **directional, low-frequency, and stop-hungry**. It is not a market-maker or HFT system. It uses a small team of LLM analysts to:

1. Read price action and perp-specific metrics (funding, OI, liquidations, order book).
2. Read macro/news context (Fed, ETF, geopolitics, Polymarket probabilities).
3. Read social/news sentiment.
4. Debate the trade, then produce a typed `PortfolioDecision`.
5. Convert the decision to a sized Hyperliquid order with a mandatory stop-loss.

The user retains control through execution modes (manual, auto-confirm, auto) and hard risk guardrails.

---

## 2. Agent Ensemble

Upstream `TradingAgents` exposes four analyst keys (`market`, `social`, `news`, `fundamentals`). For crypto perps/spot we disable `fundamentals` and use:

| Analyst | Role | Data Sources | Enabled For |
|---|---|---|---|
| **Market Analyst** | Price action + technicals | Hyperliquid candles, order book, `get_verified_market_snapshot` | All strategies |
| **Funding & OI Analyst** *(new, injected into Market or News)* | Funding, OI, liquidation clusters | Hyperliquid `funding`, `openInterest`, `liquidations` | Funding Rate Arb, all perp strategies |
| **Sentiment Analyst** | Retail + news sentiment | Yahoo/StockTwits/Reddit + `SentimentReport` | All strategies |
| **News Analyst** | Macro + event probabilities | Global news + FRED + Polymarket prediction markets | All strategies |
| **Bull / Bear Researchers** | Debate long/short cases | Synthesized analyst reports | All strategies |
| **Research Manager** | Investment plan | Bull/bear debate | All strategies |
| **Trader** | Typed transaction proposal | Research plan + analyst reports | All strategies |
| **Risk Analysts** (Aggressive/Conservative/Neutral) | Stress-test the trade | Proposal + risk context | All strategies |
| **PortfolioManager** | Final `PortfolioDecision` | Risk debate + research plan | All strategies |

### Strategy-specific analyst presets

| Template | Analysts | Extra Prompt Focus |
|---|---|---|
| **Momentum Breakout** | Market, Sentiment, News | Volume-confirmed breakouts, OI rising, funding neutral/positive, trailing stop. |
| **Mean Reversion** | Market, Sentiment | RSI/MACD extremes, liquidation wicks, tight stop. |
| **Funding Rate Arb** | Market (Funding/OI), News | Funding at extremes vs. spot, OI divergence, pair trade or fade. |
| **HYPE Delta Neutral** | Market, Funding/OI | Long perp + short spot (or inverse) to harvest funding; keep delta near zero. |
| **Custom** | User picks | User defines timeframe and stop/target rules. |

---

## 3. Prompt Strategy

### 3.1 Market Analyst prompt additions

The existing `market_analyst` prompt is technical-indicator-centric. For crypto perps, prepend the following context block (in addition to the existing instructions):

```
You are analyzing a Hyperliquid perpetual or spot market. The following crypto-specific context is available:
- Funding rate (8h): annualized cost of holding the perp; very positive means longs pay shorts, often a bearish contrarian signal near extremes.
- Open Interest (OI): total outstanding notional; rising OI with price = trend confirmation; rising OI against price = potential reversal.
- Liquidation clusters: levels where recent forced liquidations occurred; these often act as magnets or local S/R.
- Order-book imbalance: bid vs ask depth within 1% of mid price; persistent bid dominance = bullish, ask dominance = bearish.
- Spot-perp basis (if spot exists): premium/discount of perp to spot; large premium = longs overleveraged.

Use these signals together with the requested technical indicators. Be concrete: cite exact prices, funding values, OI changes, and liquidation levels. Do not invent numbers not present in the tool output.
```

### 3.2 Funding & OI Analyst (new agent/module)

Create `tradingagents/agents/analysts/funding_oi_analyst.py` or extend the Market Analyst with a new tool set. It should fetch:

- `funding(symbol)`
- `openInterest(symbol)`
- `liquidations(symbol)`
- `l2Book(symbol)` (top 10 bids/asks)

And produce a report with sections:
1. Funding regime (annualized, trend over last 7 days, percentile vs. 30d).
2. OI trend and velocity.
3. Liquidation cluster map (price, size, side).
4. Order-book imbalance (bid/ask ratio within 1%).
5. Conclusion for direction (bullish/bearish/neutral) and key levels.

### 3.3 News Analyst prompt additions

The existing `news_analyst` already receives `get_prediction_markets`. For crypto add:

```
For crypto assets, also consider:
- ETF flows (for BTC/ETH)
- Regulatory headlines
- Exchange/stablecoin flows
- Polymarket probabilities for forward-looking catalysts (Fed, elections, approvals)

Focus on events that can move the asset 5%+ in 24h. Avoid generic macro unless directly relevant.
```

### 3.4 Bull / Bear Researcher adjustments

Use the existing nodes but set `target_label` to "crypto asset". Replace "company fundamentals" with "on-chain and derivatives metrics".

### 3.5 Trader prompt

The existing `Trader` prompt already produces a `TraderProposal` with `action`, `reasoning`, `entry_price`, `stop_loss`, and `position_sizing`. Keep it, but ensure `position_sizing` is expressed as a percent of wallet (e.g. "10% of portfolio") so the execution engine can size in USDC.

### 3.6 PortfolioManager prompt additions

The existing `PortfolioManager` prompt in `tradingagents/agents/managers/portfolio_manager.py` should receive the Hyperliquid context and risk guardrails. Append to its prompt:

```
You are trading a Hyperliquid perp/spot market. You must:
- Favor trades with a clear technical setup and a stop-loss no more than 3% from entry for perps (wider for spot if justified).
- Avoid entries into illiquid or highly manipulated order books.
- Use `Underweight` / `Overweight` when conviction is moderate; reserve `Buy` / `Sell` for strong setups.
- If funding is extremely positive while price is stalling, lean short/more bearish; if funding is very negative while price is holding, lean long.
- Respect the user's max leverage and max allocation; do not propose sizes that would exceed them.
```

---

## 4. Signal-to-Order Mapping

### 4.1 Inputs

From `PortfolioDecision`:
- `rating`: `Buy`, `Overweight`, `Hold`, `Underweight`, `Sell`
- `executive_summary`: action plan
- `price_target`: optional target price
- `time_horizon`: optional holding period

From `TraderProposal`:
- `action`: `Buy`, `Hold`, `Sell`
- `entry_price`: optional
- `stop_loss`: optional
- `position_sizing`: e.g. "10% of portfolio"
- `reasoning`

From `SentimentReport`:
- `overall_band`, `overall_score`, `confidence`

From user strategy `riskConfig`:
- `maxWalletAllocation`
- `maxTradeAllocation`
- `maxLeverage`
- `mode` (paper/live)

From wallet:
- `availableBalance` (USDC)

### 4.2 Decision logic

| `PortfolioDecision.rating` | `TraderProposal.action` | Direction | Sizing base |
|---|---|---|---|---|
| Buy / Overweight | Buy | Long perp / spot buy | `position_sizing` or default 10% of wallet |
| Sell / Underweight | Sell | Short perp / spot sell | `position_sizing` or default 10% of wallet |
| Hold | Hold | No trade | 0 |
| Buy | Sell | Conflict; use `PortfolioDecision` (conservative override) | Resolve to Hold unless rationale explains arbitrage |
| Sell | Buy | Conflict; use `PortfolioDecision` | Resolve to Hold |

### 4.3 Size calculation

```python
wallet = wallet.availableBalance  # USDC
base_pct = parse_percentage(proposal.position_sizing) or strategy.defaultAllocation or 0.10
base_notional = wallet * min(base_pct, strategy.maxTradeAllocation)

if perp:
    max_lev_notional = wallet * strategy.maxWalletAllocation * strategy.maxLeverage
    notional = min(base_notional, max_lev_notional)
    margin = notional / effective_leverage
    # effective_leverage chosen by PM or capped by strategy.maxLeverage
else:
    notional = min(base_notional, wallet * strategy.maxWalletAllocation)
    margin = notional
    leverage = 1

# Ensure we don't exceed available balance
margin = min(margin, wallet * strategy.maxWalletAllocation)
```

Example:

- Wallet: $10,000
- `position_sizing`: "10% of portfolio"
- `maxTradeAllocation`: 0.10
- `maxLeverage`: 5x
- BTC price: $84,000
- Base notional: $1,000
- If PM picks 3x leverage: notional = $1,000, margin = $333.33, size = $1,000 / $84,000 ≈ 0.0119 BTC

### 4.4 Order type and price

| Scenario | Order |
|---|---|
| `entry_price` close to current mid (within 0.5%) | Limit order at `entry_price` |
| `entry_price` far or missing | Market order |
| `stop_loss` present | Attach stop-market order at `stop_loss` |
| `price_target` present | Attach take-profit limit order at `price_target` |

For Hyperliquid perp:

```python
exchange.order(
    coin=symbol,
    is_buy=direction == "long",
    sz=size,
    limit_px=limit_px if limit_order else None,
    order_type={"limit": {"tif": "Gtc"}} if limit_order else {"market": {}},
    # stop and tp are separate orders or bracket
)
```

For spot:

```python
exchange.spot_order(...)
```

### 4.5 Stop-loss rules

- **Mandatory for perps.** If `PortfolioManager` or `Trader` omits `stop_loss`, the execution engine computes one using ATR or a 3% hard default and refuses to submit without it.
- Stop must be further than Hyperliquid's minimum tick and not beyond liquidation price.
- For shorts, stop > entry; for longs, stop < entry.

### 4.6 Take-profit rules

- Optional but encouraged. Default R/R target is 1.5:1 to 2:1.
- If `price_target` is provided, use it; else compute `entry ± (entry - stop) * 1.5`.

### 4.7 No-trade rules

Do **not** submit an order if:
- `PortfolioDecision.rating` is `Hold`.
- Confidence is below a configurable threshold (default 60%).
- The setup violates `maxLeverage`, `maxTradeAllocation`, or `maxWalletAllocation`.
- Slippage estimate > configured slippage guard (1%).
- Wallet available balance < margin required.
- 24h volume < configured liquidity filter ($100k).
- Strategy has hit `maxTradesPerDay` or `cooldownMinutes` since last trade.

---

## 5. Risk Guardrails

| Guardrail | Where Enforced | Behavior |
|---|---|---|
| Paper-first | `ExecutionService` | New strategy defaults to paper; user must explicitly switch to live. |
| Max wallet allocation | `ExecutionService` | `margin <= wallet * maxWalletAllocation`. |
| Max trade allocation | `ExecutionService` | `notional <= wallet * maxTradeAllocation`. |
| Max leverage | `ExecutionService` for perps | `effective_leverage <= maxLeverage`. |
| Max daily loss | `ExecutionService` | Halt strategy for 24h if realized loss exceeds threshold. |
| Stop-loss | `ExecutionService` | No perp order without stop. |
| Take-profit | `ExecutionService` | Attach TP at 1.5–2x R/R if missing. |
| Slippage guard | `ExecutionService` | Cancel if expected fill > 1% from signal price. |
| Liquidity filter | `Scanner`/`ExecutionService` | Skip markets with 24h volume < $100k. |
| Max trades/day | `ExecutionService` | Reject signal if count exceeded. |
| Cooldown | `ExecutionService` | Reject if last trade in same market was within N minutes. |
| Kill switch | `ExecutionService` + UI | Cancel all orders, market-close perp positions. |

### 5.1 Prompt-induced conservatism

Add to `PortfolioManager` and `Trader` system prompts:

- "It is better to miss a trade than to enter without a clear stop-loss."
- "When funding is at an extreme, your directional view should fade it, not chase it."
- "If the order-book imbalance contradicts the price trend, reduce size or hold."

---

## 6. Backtest / Paper-Trading Simulation

### 6.1 Data

- Primary: Hyperliquid `candles` (1h/4h/1d) for the backtest period.
- Fallback: yfinance `BTC-USD` spot candles (note: this is not perp data; use only for rough backtests if Hyperliquid history is short).
- Funding: historical funding rates from Hyperliquid (or assume 0.01% per 8h if unavailable).

### 6.2 Signal generation in backtest

For each bar (or scheduled bar), run a simplified version of the agent pipeline:
1. Compute technical indicators on historical window.
2. Fetch funding/OI/liquidations for that date.
3. Run `PortfolioManager` (or a faster rule-based proxy) to get a decision.
4. Map decision to order using the same signal-to-order logic as live.

### 6.3 Fill model

- Market orders: fill at next bar's open.
- Limit orders: fill if price touches; else expire at end of bar.
- Fees: 0.045% taker / 0.015% maker.
- Slippage: 0.05% for market orders; 0 for limit orders.
- Funding: subtract 8h funding rate * notional for longs, add for shorts.

### 6.4 Statistics

Compute at the top of the `/backtest` page:
- Total Return
- Sharpe Ratio
- Max Drawdown
- Win Rate
- Profit Factor
- # Trades
- Avg Trade
- Benchmark Return (buy-and-hold)

---

## 7. Implementation Plan

### Phase 1 — Hyperliquid Data Adapter (Sprint 1)

1. Install `hyperliquid-python-sdk` in the project.
2. Create `tradingagents/dataflows/hyperliquid.py`:
   - `get_stock_data(symbol, start, end)` → candles CSV
   - `get_indicators(...)` → OHLCV-derived technicals
   - `get_funding(symbol)`, `get_open_interest(symbol)`, `get_orderbook(symbol)`, `get_recent_trades(symbol)`, `get_liquidations(symbol)`
3. Create `tradingagents/agents/utils/hyperliquid_data_tools.py` with `@tool` wrappers.
4. Add `hyperliquid` to `VENDOR_LIST` and `VENDOR_METHODS` in `dataflows/interface.py`.
5. Add `hyperliquid` config option to `default_config.py` under `data_vendors`.
6. Add `tradingagents/agents/analysts/funding_oi_analyst.py` and wire it into the analyst factories and execution plan.
7. Add tests: `tests/test_hyperliquid_dataflow.py`, `tests/test_funding_oi_analyst.py`.

### Phase 2 — Backend API (Sprint 1/2)

1. Create `backend/main.py` FastAPI app.
2. Add endpoints:
   - `GET /api/markets` → live Hyperliquid market list
   - `GET /api/markets/{symbol}` → price, 24h, funding, OI
   - `POST /api/analyze` → run `TradingAgentsGraph` and return `Signal` JSON
   - `GET /api/wallets`, `POST /api/wallets`
   - `GET /api/strategies`, `POST /api/strategies`
   - `POST /api/backtest`
   - `POST /api/execute` (paper or live)
3. Add `backend/services/signal_service.py` to run the graph and map output.
4. Add `backend/services/execution_service.py` for paper/live order simulation and submission.

### Phase 3 — Frontend Wiring (Sprint 2)

1. Update `frontend/src/services/api.ts` to call real FastAPI endpoints.
2. Add `/strategies` and `/backtest` pages.
3. Update `/scanner` to use live market data and trigger `/api/analyze`.
4. Update `/signals` to display `PortfolioDecision`/`TraderProposal`/`SentimentReport`.
5. Update `/positions` and `/orders` from Hyperliquid `clearinghouseState`.

### Phase 4 — Strategy Builder + Backtest (Sprint 2/3)

1. Implement strategy templates and builder UI.
2. Implement backtest engine with statistics at top.
3. Add paper/live toggle and execution mode selector.

### Phase 5 — Multi-Wallet + Auto-Trading (Sprint 4/5)

1. Wallet manager UI and encrypted secret storage.
2. Auto-trading scheduler with cooldown and daily limits.
3. Live order signing with `hyperliquid-python-sdk`.
4. Kill switch and risk dashboard.

### Phase 6 — Alerts + Reflection (Sprint 6)

1. In-app and Telegram/Discord alerts.
2. `reflect_and_remember()` integration on closed trades.
3. `/memory` page.

---

## 8. Open Questions / Assumptions

1. **Funding & OI analyst**: Should it be a separate analyst node or injected as extra tools into the Market Analyst? Separate node is cleaner but adds latency.
2. **LLM model choice**: For fast iteration use `gpt-5.4-mini` or `claude-haiku-4-5`; for final decisions use a stronger model. The builder should expose this pair.
3. **Hyperliquid historical candles**: How far back and at what granularity? If limited, backtests may use spot data as a proxy.
4. **Testnet**: Does Hyperliquid have a public testnet for paper trading, or do we simulate against live mids?
5. **Order-book data in prompts**: LLMs struggle with raw L2 snapshots. We should pre-aggregate to bid/ask ratio within 1% and top-of-book depth before feeding to agents.
6. **Perp vs spot symbol handling**: Hyperliquid uses `BTC` for perps and `HYPE/USDC` for spot. `TradingAgents` uses `BTC-USD`. We need a symbol map per strategy.

---

## 9. First Concrete Step

Start **Phase 1** by implementing `tradingagents/dataflows/hyperliquid.py` and a FastAPI `/api/analyze` endpoint. This gives an immediate end-to-end demo: frontend scanner → backend → `TradingAgentsGraph` with Hyperliquid data → typed signal → UI.
