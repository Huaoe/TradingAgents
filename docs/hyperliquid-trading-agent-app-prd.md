# Hyperliquid Trading Agent App PRD
## Personal AI Trading Terminal for Hyperliquid

**Author:** Devin (Thomas Berrod session)  
**Date:** 2026-08-12  
**Status:** Draft — aligned with upstream `TradingAgents` v0.3.1  
**Related:** `Huaoe/TradingAgents` + `hyperliquid-python-sdk`

---

## 1. Executive Summary

Build a focused web app that turns `TradingAgents` into a personal, wallet-controlled trading bot for **Hyperliquid**. The app lets the user create or pick strategies, backtest them, run a multi-agent LLM pipeline for perp/spot markets, optionally auto-execute signals, manage multiple wallets, and track PnL — all with strict risk guardrails.

This version of the PRD is rewritten to **reuse the upstream `TradingAgents` v0.3.1** capabilities:
- Native crypto asset mode (`BTC-USD`, `SOL-USD`, ...).
- Multi-provider LLM client registry and model catalog.
- Structured-output schemas (`TraderProposal`, `PortfolioDecision`, `SentimentReport`).
- `PortfolioManager` agent that already synthesizes risk-analyst debate into a typed final decision.
- Polymarket/prediction-markets dataflow for macro/event context.
- Symbol normalization and a robust test/CI setup.

The pieces we still need to add are:
- A **Hyperliquid data adapter** that feeds perp/spot prices, funding, open interest, and order-book data into `TradingAgents`.
- An **execution service** that signs and submits orders to Hyperliquid using the user's API wallet.
- A **React frontend** that exposes strategy, backtest, signal, wallet, and auto-trading controls.

---

## 2. Problem Statement

`TradingAgents` v0.3.1 already:
- Detects crypto tickers (`BTC-USD`, `ETH-USD`) and disables equity-only analysts (fundamentals).
- Produces a typed `PortfolioDecision` with `Buy / Overweight / Hold / Underweight / Sell`.
- Supports many LLM providers via a registry/catalog.
- Adds prediction-market context from Polymarket.

What it **does not** do:
- Read **Hyperliquid-native** market data (perp prices, funding, OI, liquidations, order book).
- Manage **wallets** or submit **orders** to an exchange.
- Provide a **strategy builder/backtest UI** or **auto-trading controls**.

This app closes those gaps while keeping the upstream graph and schemas.

---

## 3. Goals

| # | Goal | Success Metric |
|---|---|---|
| 1 | Run `TradingAgents` against Hyperliquid perp/spot markets with native perp data. | Signal latency < 30s per market. |
| 2 | Let users build strategies from templates or custom parameters. | Launch a backtest in < 2 minutes. |
| 3 | Convert `PortfolioDecision`/`TraderProposal` into Hyperliquid orders, automatically or with one-click approval. | Order success rate > 95% after paper validation. |
| 4 | Support multiple wallets/accounts with per-wallet allocation and risk settings. | Switch wallet in < 3 clicks. |
| 5 | Prove alpha with backtests and paper trading before live capital. | Backtest page shows Sharpe, drawdown, win rate at the top. |
| 6 | Protect capital with hard risk guardrails. | Max drawdown per strategy < user-defined X% (default 10%). |
| 7 | Be operable by a single user with their own wallet. | < 5 minutes from onboarding to first running strategy. |

---

## 4. Leveraging Upstream v0.3.1

| Upstream Feature | How we use it |
|---|---|
| `AssetType.CRYPTO` + `detect_asset_type` (`-USD`, `-USDT`, `-USDC`) | Run the graph in crypto mode; fundamentals analyst is filtered out automatically. |
| `normalize_symbol` in `tradingagents/dataflows/symbol_utils.py` | Accept user symbols like `BTCUSD`, `BTC-USD`, `BTC-USDT` and resolve them to `BTC-USD` for Yahoo or to `BTC` for Hyperliquid. |
| `llm_clients` + `model_catalog.py` | Populate the strategy builder's LLM provider/model dropdowns. |
| `TraderProposal` / `PortfolioDecision` in `tradingagents/agents/schemas.py` | Treat these as the signal schema between the agent graph and the execution engine. |
| `PortfolioManager` in `tradingagents/agents/managers/portfolio_manager.py` | Reuse the risk-analyst judge instead of writing a new one. |
| `SentimentReport` from `sentiment_analyst.py` | Display sentiment band, score, and confidence in the signal feed. |
| Polymarket dataflow + `get_prediction_markets` | Add macro/event context to the `news_analyst` for crypto catalysts (Fed, elections, ETF approvals). |
| `dataflows/interface.py` vendor routing | Add `hyperliquid` as a new `core_stock_apis` / `technical_indicators` vendor behind the same `route_to_vendor` calls. |
| `tests/` + `pytest` + GitHub Actions | Keep the same testing discipline; add tests for the Hyperliquid adapter and execution service. |

---

## 5. Target User

A single, technically comfortable crypto trader who:
- Wants to run LLM agents on Hyperliquid perp/spot markets.
- Wants a strategy library, backtests, and auto-trading controls in one UI.
- Holds funds in their own wallet and only shares an encrypted API-wallet secret.

---

## 6. Supported Markets

| Market | Instruments | Use Case |
|---|---|---|
| **Perpetuals** | `BTC`, `ETH`, `SOL`, and all Hyperliquid perp pairs | Directional long/short with leverage |
| **Spot** | Hyperliquid spot pairs (e.g. `HYPE/USDC`, `PURR/USDC`) | Spot swing / accumulation |

User-facing symbols should map to Hyperliquid's `coin` names (`BTC`, `ETH`, `SOL`, `HYPE`, `PURR`, ...). For `TradingAgents` we can pass the equivalent Yahoo symbol (`BTC-USD`) to the upstream graph when using Yahoo as a fallback, and pass the raw `BTC` coin to the Hyperliquid adapter.

---

## 7. Agent Pipeline (Reusing Upstream)

```
User picks strategy
  ├─ symbol normalized (BTCUSD -> BTC for HL, BTC-USD for Yahoo)
  ├─ TradingAgentsGraph.run() with asset_type=CRYPTO
  │   ├─ Market Analyst (uses Hyperliquid candles/order book)
  │   ├─ Sentiment Analyst (news + StockTwits + Reddit)
  │   ├─ News Analyst (news + Polymarket macro context)
  │   ├─ Bull / Bear Researchers
  │   ├─ Trader -> TraderProposal
  │   ├─ Aggressive / Conservative / Neutral Risk Analysts
  │   └─ PortfolioManager -> PortfolioDecision
  └─ Execution engine converts PortfolioDecision -> Hyperliquid order
```

### Hyperliquid-specific data sources

| Agent | Responsibility | Hyperliquid Info API |
|---|---|---|
| **Market Data Analyst** | OHLCV, order book depth, recent trades | `candles`, `l2Book`, `recentTrades`, `allMids` |
| **Funding & OI Analyst** | Funding rates, open interest, liquidations | `funding`, `openInterest`, `liquidations` |
| **News + Polymarket Analyst** | Macro/event context | `get_prediction_markets` (Polymarket via existing tool) |
| **Sentiment Analyst** | News, StockTwits, Reddit | existing `sentiment_analyst.py` |
| **Risk Analysts** | Position sizing, leverage, drawdown | `clearinghouseState`, user margin |
| **PortfolioManager** | Final `PortfolioDecision` | reuses upstream node |

The new code we add is mostly:
- A `hyperliquid` vendor in `dataflows/interface.py`.
- A `HyperliquidDataFlow` module that implements the same functions as `yfinance` (or narrower set) so the agents can consume perp/spot data transparently.

---

## 8. Core Features

### 8.1 Strategy Library & Builder

**Predefined Templates**

| Template | Default Settings |
|---|---|
| **Momentum Breakout** | Market + Sentiment + News agents; enter on volume-confirmed breakouts; trailing stop. |
| **Mean Reversion** | Market + Sentiment; RSI/MACD extremes; tight stop. |
| **Funding Rate Arb** | Funding/OI analyst + News; fade/revert extreme funding. |
| **HYPE Delta Neutral** | Long perp + short spot (or vice versa) on HYPE to harvest funding. |
| **Custom** | User picks agents, LLM, risk, schedule. |

**Builder Parameters**
- Markets / watchlist.
- Agent ensemble (Market, Funding/OI, Sentiment, News).
- LLM provider and model (populated from `model_catalog.py`).
- Risk: max wallet allocation, max trade allocation, max leverage, stop-loss %, take-profit %, max daily loss, max trades/day, cooldown.
- Execution mode: Manual / Auto-confirm / Fully automatic.
- Schedule: on demand / every N min / at event (funding reset, 4h close).
- Assigned wallet.
- Paper vs. live.

### 8.2 Multi-Wallet Support

- Add multiple Hyperliquid API wallets, label them ("Main", "Aggressive", etc.).
- Encrypted secret storage (local keyring/AES with master password).
- Per-wallet balances, positions, PnL.
- Default wallet per strategy; global wallet switcher.

### 8.3 Auto-Trading Engine

- Manual: signal appears in feed, user accepts/rejects.
- Auto-confirm: signal executes unless user cancels within N seconds.
- Fully automatic: signal executes immediately if it passes risk filters.
- Schedule/cooldown/daily trade limits.
- Bracket orders (stop-loss + take-profit) placed after entry.
- Start / pause / stop per strategy.

### 8.4 Market Scanner

- Grid of Hyperliquid markets: price, 24h, volume, funding, OI, signal, confidence.
- Filters and sorting.
- One-click **Analyze** runs the `TradingAgentsGraph` for that coin.

### 8.5 Signal Feed

- Card per signal showing:
  - `Buy / Overweight / Hold / Underweight / Sell` from `PortfolioDecision`.
  - Confidence, size, leverage, entry, stop, target.
  - Agent reasoning and `SentimentReport` band/score.
- Accept / edit / reject / auto-execute.

### 8.6 Backtesting Interface

**Statistics at the top of the page**

| Metric | Description |
|---|---|
| Total Return | Cumulative strategy return |
| Sharpe Ratio | Risk-adjusted return |
| Max Drawdown | Largest peak-to-trough decline |
| Win Rate | % winning trades |
| Profit Factor | Gross profit / gross loss |
| # Trades | Closed trades |
| Avg Trade | Mean PnL per trade |
| Benchmark Return | Buy-and-hold / HODL return |

**Below the statistics**
- Equity curve vs. benchmark.
- Drawdown chart.
- Monthly returns heatmap.
- Sortable trade list with entry/exit, PnL, duration, reasoning.
- "Activate as Strategy" button.

### 8.7 Portfolio & Positions

- Open perp/spot positions across wallets.
- Unrealized/realized PnL, margin, available balance.
- Open orders with cancel.
- Funding payments and fill history.
- Per-strategy and per-wallet PnL attribution.

### 8.8 Reflection & Memory

- After a closed trade, feed realized return to `reflect_and_remember()`.
- Memory browser in UI.

### 8.9 Alerts

- In-app, Telegram, Discord, email for signals, fills, stop hits, risk breaches.

---

## 9. User Flow

```
Onboarding
  ├─ Add Hyperliquid API wallet(s)
  ├─ Set risk guardrails and default paper mode
  └─ Fund Hyperliquid account(s)

Strategy Library
  ├─ Pick template or custom
  ├─ Configure markets, agents, LLM, risk, execution mode, wallet
  ├─ Save & Backtest
  └─ Activate (paper or live)

Market Scanner
  └─ Analyze a market -> Signal Feed

Signal Feed
  └─ Manual accept / Auto-execute -> Order Preview -> Portfolio

Backtest Lab
  └─ Select strategy + date range -> View top stats -> Activate
```

---

## 10. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Vite + React + TypeScript + Tailwind Frontend                             │
│  Dashboard, scanner, strategy builder, backtest, signals, positions        │
├─────────────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Python)                                                    │
│  - Strategy, wallet, backtest, alert CRUD                                   │
│  - Orchestrates TradingAgentsGraph.run(asset_type=CRYPTO, symbol=...)       │
│  - Converts PortfolioDecision / TraderProposal to Hyperliquid orders        │
│  - Signs/submits via hyperliquid-python-sdk                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  TradingAgents Core (upstream v0.3.1)                                       │
│  - crypto asset mode, multi-provider LLM clients, structured schemas        │
│  - PortfolioManager, SentimentReport, Polymarket tool                       │
│  - Memory + reflection                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Hyperliquid Data & Execution Layer (new)                                   │
│  - Info API client: candles, order book, funding, OI, clearinghouseState    │
│  - Exchange client: signed perp/spot orders, leverage, cancel               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Backend Services

| Service | Responsibility |
|---|---|
| **Wallet Service** | Encrypted API-wallet secrets, balance sync. |
| **Strategy Service** | Templates, builder, versioning, scheduling. |
| **Signal Service** | Wrap `TradingAgentsGraph.run()` and normalize `PortfolioDecision`/`TraderProposal`. |
| **Execution Service** | Build, sign, submit Hyperliquid orders; track fills. |
| **Data Service** | Hyperliquid Info reads + caching; fallback to yfinance for spot. |
| **Backtest Service** | Historical sim with fees/slippage and stats. |
| **Portfolio Service** | Sync `clearinghouseState`, compute PnL per wallet. |
| **Alert Service** | Notifications. |

---

## 11. Hyperliquid Integration Details

### SDK

- `hyperliquid-python-sdk`.
- `Info` client for reads.
- `Exchange` client for signed writes.
- Testnet and mainnet support.

### Read Operations

| Endpoint | Purpose |
|---|---|
| `allMids` | Current mid prices |
| `candles` | OHLCV history |
| `l2Book` | Order book depth |
| `funding` | Funding rate history |
| `openInterest` | OI per asset |
| `liquidations` | Recent liquidations |
| `clearinghouseState` | User margin, positions, balances |
| `orderStatus` | Order status |

### Write Operations

| Operation | SDK Method |
|---|---|
| Place perp order | `exchange.order()` |
| Place spot order | `exchange.spot_order()` |
| Set leverage | `exchange.update_leverage()` |
| Cancel order | `exchange.cancel()` |

### Wallet Setup

- User creates an API wallet in Hyperliquid UI.
- App stores encrypted API-wallet secret only.
- Main wallet seed never leaves the user's custody.
- Orders signed EIP-712 by the SDK.

### Fees

- Base: ~0.045% taker / 0.015% maker.
- Backtests/paper trading must model these.

---

## 12. Risk & Safety Guardrails

| Guardrail | Default | Behavior |
|---|---|---|
| Paper-first | On | New strategy must paper trade 7 days before live. |
| Max wallet allocation | 25% | Strategy cannot use more. |
| Max trade allocation | 10% | Single trade limit. |
| Max leverage | 5x | Cap per perp. |
| Max daily loss | 5% wallet / 2% strategy | Halt for 24h. |
| Stop-loss | Required | No order without stop. |
| Take-profit | Recommended | Encourage 1.5–2x R/R. |
| Slippage guard | 1% | Cancel if fill > 1% from signal. |
| Liquidity filter | $100k+ 24h volume | Avoid illiquid pairs. |
| Max trades/day | 10 | Limit churn. |
| Cooldown | 5 min | Between new trades in same market. |
| Kill switch | Manual | Cancel all orders, flatten positions. |

---

## 13. Data Model

```
User
 ├─ wallets: Wallet[]
 ├─ defaultWalletId
 └─ riskProfile

Wallet
 ├─ id, label, address, encryptedSecret
 ├─ type (api | subaccount)
 └─ isPaper

Strategy
 ├─ id, name, isTemplate, template
 ├─ markets: string[]
 ├─ agents: string[]
 ├─ llmProvider, llmModel
 ├─ executionMode (manual | auto_confirm | automatic)
 ├─ schedule
 ├─ walletId
 ├─ riskConfig
 ├─ mode (paper | live)
 ├─ backtestResult?: BacktestResult
 └─ createdAt, updatedAt

Signal
 ├─ strategyId, walletId, market
 ├─ decision: PortfolioDecision
 ├─ proposal: TraderProposal
 ├─ sentiment?: SentimentReport
 ├─ confidence, size, leverage, entry, stop, target
 ├─ reasoning
 └─ timestamp

Order
 ├─ signalId, walletId
 ├─ hyperliquidOrderId (oid)
 ├─ market, side, size, price, orderType
 ├─ status (pending / filled / partial / cancelled / failed)
 ├─ fillPrice, fee, slippage
 └─ txTimestamp

Position
 ├─ walletId, market, side, size, entryPrice
 ├─ unrealizedPnl, realizedPnl
 ├─ liquidationPrice (perps)
 ├─ leverage, marginUsed
 ├─ strategyId
 └─ lastUpdated

Trade
 ├─ openOrderId, closeOrderId
 ├─ strategyId, walletId, market
 ├─ pnl, returnPct, duration
 └─ closedAt

BacktestResult
 ├─ strategyId, startDate, endDate
 ├─ totalReturn, sharpe, maxDrawdown, winRate, profitFactor, tradeCount, avgTrade
 ├─ benchmarkReturn
 ├─ equityCurve, drawdowns, trades
 └─ createdAt
```

---

## 14. Page Map

| Route | Purpose |
|---|---|
| `/` | Dashboard: combined & per-wallet portfolio, active strategies |
| `/strategies` | Strategy library and builder |
| `/strategies/:id` | Strategy detail, backtests, activation |
| `/scanner` | Hyperliquid market scanner |
| `/signals` | Signal feed and execution queue |
| `/orders` | Open orders and fill history |
| `/positions` | Current positions and PnL per wallet |
| `/backtest` | Backtest lab with statistics at the top |
| `/wallets` | Wallet manager |
| `/memory` | Agent reflection memory browser |
| `/settings` | Defaults, alerts, LLM config |

---

## 15. Non-Functional Requirements

- **Latency:** Signal < 30s per market; order submission < 3s.
- **Uptime:** Backend 99.5% during market hours; retries on Hyperliquid failures.
- **Security:** Encrypted secrets at rest; no plaintext keys in logs; no custody of main wallet.
- **Audit:** Every signal, order, override, and strategy change logged.
- **Cost:** Cache Info API calls; use cheaper LLMs (`gpt-5.4-mini`, `claude-haiku-4-5`) for quick tasks.
- **Compliance:** Not financial advice disclaimers; user must acknowledge live trading risks.

---

## 16. Roadmap

| Phase | Scope | Time |
|---|---|---|
| **V0 — Data Adapter** | Add `hyperliquid` vendor to `dataflows/interface.py`; implement candles/OB/funding/OI reads; update Market Scanner | Week 1 |
| **V1 — Strategy Builder + Backtest** | Strategy templates, builder, backtest UI with top statistics | Week 2 |
| **V2 — Multi-Wallet + Paper Trading** | Wallet manager, paper execution, portfolio tracking | Week 3 |
| **V3 — Signal + Auto-Trading** | Wire `TradingAgentsGraph` with `asset_type=CRYPTO`; signal feed; auto/manual execution | Week 4 |
| **V4 — Live Trading + Risk** | Signed Hyperliquid orders, risk guardrails, kill switch | Week 5 |
| **V5 — Alerts + Reflection + Polish** | Telegram/Discord alerts, reflection loop, mobile UI, onboarding | Week 6+ |

---

## 17. Open Questions

1. Do we add a `hyperliquid` vendor to the upstream `dataflows/interface.py`, or keep the adapter in a separate `hyperliquid` service that feeds the graph?
2. Should backtests use Hyperliquid historical candles (limited history) or yfinance spot data as a proxy for perps?
3. Which Hyperliquid testnet is available for paper trading, or do we simulate fills against live mid prices?
4. Do we want a second confirmation (email/2FA) before any live auto-trade?
5. Should the strategy builder expose **all** `model_catalog` providers, or restrict to a curated subset?

---

## 18. Next Steps

1. Implement `tradingagents/dataflows/hyperliquid.py` with `get_stock_data`, `get_indicators`, `get_funding`, `get_open_interest`, `get_orderbook`.
2. Register `hyperliquid` as a vendor in `dataflows/interface.py` and `default_config.py`.
3. Build a FastAPI endpoint `/api/signals/{symbol}` that runs `TradingAgentsGraph` in crypto mode and returns `PortfolioDecision` + `TraderProposal` + `SentimentReport`.
4. Add the strategy builder and backtest page to the existing React frontend.
5. Implement encrypted wallet storage and the Hyperliquid `ExecutionService`.
6. Run 7 days of paper trading before enabling live signing.
