# Hyperliquid Trading Agent App PRD
## Personal AI Trading Terminal for Hyperliquid

**Author:** Devin (Thomas Berrod session)  
**Date:** 2026-08-12  
**Status:** Draft — feature-complete for V1 scope  
**Related:** `Huaoe/TradingAgents` + Hyperliquid Python SDK

---

## 1. Executive Summary

Build a focused web app that extends `TradingAgents` to trade **Hyperliquid** markets using the user's own crypto wallet. The app acts as a personal command center: it runs multi-agent LLM analysis on selected perp/spot markets, optionally auto-executes signals, supports multiple wallets/accounts, provides a backtesting interface with statistics at the top, and lets users create, save, and run both predefined and custom strategies — all under strict user-controlled risk guardrails.

This is the **fastest path to real money** from the TradingAgents framework because Hyperliquid provides:
- Wallet-based authentication (no CEX KYC or API key required).
- A native Python SDK.
- Perpetuals + spot in one venue.
- Low latency and low fees.

---

## 2. Problem Statement

`TradingAgents` currently:
- Generates textual `BUY / SELL / HOLD` signals for equities.
- Has no execution layer, no perp/crypto data, no wallet integration, and no multi-account support.
- Runs from the CLI with no portfolio tracking, no strategy library, and no backtest UI.

To trade Hyperliquid with it, we need a product layer that:
1. Feeds Hyperliquid market data into the agents.
2. Lets users choose from proven strategies or build their own.
3. Parses agent output into sized Hyperliquid orders (market/limit, size, leverage, stop, take-profit).
4. Can run fully automatically or with human confirmation.
5. Supports multiple wallets/accounts and capital allocation across them.
6. Provides a backtesting UI with headline performance statistics.
7. Tracks positions, PnL, and strategy performance.
8. Protects the user from blow-ups.

---

## 3. Goals

| # | Goal | Success Metric |
|---|---|---|
| 1 | Run TradingAgents against Hyperliquid perp/spot markets daily or on-demand. | Signal latency < 30s per market. |
| 2 | Offer a library of predefined strategies plus a custom strategy builder. | User can launch a backtest in < 2 minutes. |
| 3 | Convert signals into executable Hyperliquid orders automatically or with one-click approval. | Order submission success rate > 95% after paper validation. |
| 4 | Support multiple wallets/accounts with per-wallet allocation and risk settings. | Switch wallet and strategy in < 3 clicks. |
| 5 | Prove alpha with paper trading & backtests before live capital. | Backtest page shows Sharpe, drawdown, win rate at the top. |
| 6 | Protect capital with hard risk guardrails. | Max drawdown per strategy < user-defined X% (default 10%). |
| 7 | Be operable by a single user with their own wallet. | < 5 minutes from login to first running strategy. |

---

## 4. Target User

A single, technically comfortable crypto trader who wants to:
- Automate directional perp/spot strategies on Hyperliquid.
- Choose from proven strategy templates or design custom agents.
- Run strategies across multiple wallets/accounts.
- Backtest and validate strategies before risking capital.
- Understand *why* the AI is entering or exiting a position.
- Retain full custody of funds via their own wallet.

---

## 5. Supported Markets

| Market | Instruments | Use Case |
|---|---|---|
| **Perpetuals** | `BTC`, `ETH`, `SOL`, and other Hyperliquid perp pairs | Directional long/short with leverage |
| **Spot** | Hyperliquid spot pairs (e.g. `HYPE/USDC`, `PURR/USDC`) | Spot swing / accumulation |

---

## 6. New Agent Modules for Hyperliquid

Extend `TradingAgents` with Hyperliquid-aware analysts. Each analyst maps to one or more Hyperliquid `Info` API calls.

| Agent | Responsibility | Data Source |
|---|---|---|
| **Market Data Analyst** | Price action, OHLCV, order book depth, recent trades | `allMids`, `candles`, `l2Book`, `recentTrades` |
| **Funding & OI Analyst** | Funding rates, open interest, liquidation maps | `funding`, `openInterest`, `liquidations` |
| **On-Chain/Sentiment Analyst** | Exchange flows, social sentiment, macro news | Glassnode/Dune (optional), X/Reddit, CoinDesk |
| **Technical Analyst** | RSI, MACD, volume profile, support/resistance | Candles from Hyperliquid or computed locally |
| **Risk Analyst** | Position sizing, leverage, drawdown, liquidation distance | `clearinghouseState`, user margin data |
| **Trader** | Final order plan: action, size, entry, stop, target | Synthesizes all analyst reports + past memory |
| **Risk Manager** | Approves/rejects the trade against risk rules | Internal risk config |

All agents use the existing LangGraph debate + reflection framework.

---

## 7. Core Features

### 7.1 Strategy Library & Builder

A central place to browse, clone, create, backtest, and activate strategies.

**Predefined Strategy Templates**

| Template | Description | Default Markets |
|---|---|---|
| **Momentum Breakout** | Enter on volume-confirmed breakouts with trailing stops. | BTC, ETH, SOL perps |
| **Mean Reversion** | Counter-trend entries at RSI extremes with tight stops. | BTC, ETH perps |
| **Funding Rate Arb** | Go long/short based on funding-rate extremes vs. spot. | High-funding perps + spot |
| **HYPE Delta Neutral** | Long perp / short spot (or vice versa) to harvest funding. | HYPE perp + spot |
| **Custom** | User-defined agent ensemble, indicators, and risk rules. | Any |

Each template exposes editable parameters:
- Markets / watchlist.
- Timeframe and lookback.
- Agent ensemble (which analysts to include).
- LLM provider and models (deep thinker + quick thinker).
- Risk parameters: max allocation, max leverage, max daily loss, stop-loss, take-profit, direction filter.
- Execution mode: manual, auto-confirm, or fully automatic.
- Paper vs. live.

**Builder Flow**
1. User picks a template or starts from scratch.
2. Configure parameters on a single form.
3. Save draft.
4. Run backtest (see 7.6).
5. Activate as paper or live strategy.

### 7.2 Multi-Wallet / Multi-Account Support

- Add multiple Hyperliquid wallets/accounts:
  - Main trading wallet.
  - API wallets (one per strategy to limit risk).
  - Sub-accounts (if Hyperliquid supports them).
- Label wallets (e.g. "Main", "Aggressive", "Conservative").
- Assign a default wallet per strategy.
- Dashboard shows combined or per-wallet PnL.
- Capital allocation per wallet: % of wallet balance a strategy may use.
- All private keys/API wallet secrets encrypted at rest.

### 7.3 Auto-Trading Engine

- Each strategy can run in one of three modes:
  - **Manual** — generate signal, wait for user accept/reject.
  - **Auto-confirm** — show signal and execute if user does not cancel within N seconds.
  - **Fully automatic** — execute immediately when signal passes all risk filters.
- Schedule strategies to run:
  - On demand.
  - Every N minutes/hours.
  - At market events (e.g. funding reset, 4h candle close).
- Cooldown / anti-overtrade guard: max N trades per day, min hold time.
- Post-execution actions: set stop-loss/take-profit bracket orders automatically.
- One-click start / pause / stop per strategy.
- Activity log: every signal, override, and execution.

### 7.4 Market Scanner

- Grid of Hyperliquid perp and spot markets.
- Columns: last price, 24h change, funding rate, open interest, agent signal, confidence.
- Filters: market type, signal direction, confidence threshold, volatility.
- One-click "Analyze" to run the full TradingAgents graph for that market.
- Bulk "Run Strategy" on selected markets.

### 7.5 Signal Feed

- Card per market showing:
  - `BUY / SELL / HOLD` with confidence %.
  - Recommended size in USDC and as % of account.
  - Recommended leverage (perps only).
  - Suggested entry, stop-loss, take-profit.
  - Agent reasoning summary.
- User can accept, edit, or reject the signal.
- Auto-execution history and pending queue.

### 7.6 Backtesting Interface

A dedicated page with **headline statistics at the top** followed by detailed charts and trade data.

**Statistics Header (top of the page)**

| Metric | Description |
|---|---|
| **Total Return** | Cumulative strategy return vs. benchmark |
| **Sharpe Ratio** | Risk-adjusted return |
| **Max Drawdown** | Largest peak-to-trough decline |
| **Win Rate** | % of winning trades |
| **Profit Factor** | Gross profit / gross loss |
| **# Trades** | Total closed trades |
| **Avg Trade** | Average PnL per trade |
| **Benchmark Return** | Buy-and-hold return for the same period |

**Below the statistics**
- Equity curve vs. benchmark.
- Drawdown chart.
- Monthly returns heatmap.
- Trade list with entry/exit, PnL, duration, reasoning.
- Parameter sensitivity table.
- Walk-forward / out-of-sample selector.
- "Activate as Strategy" button after successful backtest.

### 7.7 Order Preview & Execution

- On signal accept or auto-trigger, show an order preview:
  - Market or limit order.
  - Estimated size, notional, margin, fees (~0.045% taker / 0.015% maker).
  - Slippage estimate from order book.
  - Post-trade account margin and liquidation price (perps).
- One-click "Execute" or "Paper Execute".
- Orders are signed via the Hyperliquid Python SDK using the wallet assigned to the strategy.

### 7.8 Portfolio & Positions

- Real-time view of open perp/spot positions across all wallets.
- Unrealized/realized PnL, margin used, available margin.
- Open orders list with cancel buttons.
- Funding payments history.
- Fills history.
- Per-strategy and per-wallet PnL attribution.

### 7.9 Reflection & Memory

- After a position closes, feed realized returns back to `reflect_and_remember()`.
- Memory browser: what did the agents learn, which agents are contributing positively.
- User can flag a bad trade to update agent memory.

### 7.10 Alerts

- In-app, email, Telegram, or Discord alerts for:
  - New signals.
  - Executed orders.
  - Stop-loss / take-profit hits.
  - Risk threshold breaches.
  - Strategy started/stopped.

---

## 8. User Flow

```
Onboarding
  ├─ Connect or generate Hyperliquid API wallet(s)
  ├─ Set risk guardrails and default paper/live mode
  └─ Fund Hyperliquid account(s)

Dashboard
  ├─ Combined & per-wallet portfolio snapshot
  ├─ Active strategies with start/pause/stop
  └─ Latest signals

Strategy Library
  ├─ Pick predefined template or custom
  ├─ Configure parameters
  ├─ Save & Backtest
  └─ Activate (paper or live)

Market Scanner
  └─ Analyze a market → Signal Feed

Signal Feed
  └─ Manual accept / Auto-execute → Order Preview → Portfolio

Backtest Lab
  └─ Select strategy + date range → View top statistics → Activate
```

---

## 9. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Vite + React + TypeScript + Tailwind Frontend                         │
│  - Dashboard, scanner, strategy builder, signal feed, backtest, portfolio │
├─────────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Python)                                               │
│  - Orchestrates TradingAgents graph per strategy                       │
│  - Wraps Hyperliquid Python SDK for order execution                    │
│  - Manages wallets, strategies, backtests, positions, alerts           │
├─────────────────────────────────────────────────────────────────────────┤
│  TradingAgents Core (LangGraph)                                        │
│  - Hyperliquid data adapters                                           │
│  - New perp/spot analyst and risk agents                               │
│  - Memory (ChromaDB) and reflection                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  Hyperliquid Network                                                   │
│  - Info API (read-only, no auth)                                       │
│  - Exchange API (signed orders via user wallet)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Backend Services

| Service | Responsibility |
|---|---|
| **Wallet Service** | Store encrypted keys, fetch balances, support multiple accounts. |
| **Strategy Service** | Templates, custom builder, versioning, activation, scheduling. |
| **Signal Service** | Run the TradingAgents graph and normalize output. |
| **Execution Service** | Build, sign, and submit Hyperliquid orders; track fills. |
| **Data Service** | Fetch candles, order book, funding, OI from Hyperliquid Info API; cache locally. |
| **Portfolio Service** | Sync `clearinghouseState` and open orders; compute PnL per wallet. |
| **Backtest Service** | Historical simulation with fee/slippage model and performance stats. |
| **Alert Service** | Webhooks / Telegram / Discord / email notifications. |

---

## 10. Hyperliquid Integration Details

### 10.1 SDK

- Use `hyperliquid-python-sdk`.
- `Info` client for all reads.
- `Exchange` client for all signed writes.
- Supports both testnet and mainnet.

### 10.2 Read Operations

| Endpoint | Purpose |
|---|---|
| `allMids` | Current mid prices |
| `candles` | OHLCV history |
| `l2Book` | Order book depth |
| `funding` | Funding rate history |
| `openInterest` | OI per asset |
| `liquidations` | Recent liquidation data |
| `clearinghouseState` | User margin, positions, balances |
| `orderStatus` | Status of a placed order |

### 10.3 Write Operations

| Operation | SDK Method | Notes |
|---|---|---|
| Place perp order | `exchange.order()` | Specify `coin`, `is_buy`, `sz`, `limit_px`, `order_type` |
| Place spot order | `exchange.spot_order()` | Use spot token format |
| Set leverage | `exchange.update_leverage()` | Per-asset leverage |
| Cancel order | `exchange.cancel()` | By `coin` and `oid` |
| Transfer spot↔perp | `exchange.usd_class_transfer()` | Manage USDC between wallets |

### 10.4 Wallet Setup

- User generates an **API wallet** from the Hyperliquid UI per strategy or account.
- App stores only the API-wallet private key, never the main wallet seed.
- Private key is encrypted at rest (e.g. AWS KMS / HashiCorp Vault / local keyring).
- All transactions are EIP-712 signed by the SDK.

### 10.5 Fees

- Base tier: **0.045% taker / 0.015% maker**.
- Volume tiers and `HYPE` staking can reduce fees further.
- Strategy backtests and paper trading must model these fees.

---

## 11. Risk & Safety Guardrails

These are non-negotiable and enforced before any live order.

| Guardrail | Default | Behavior |
|---|---|---|
| Paper-first mode | On | Every new strategy must paper trade for 30 days before live. |
| Per-wallet max allocation | 25% | Strategy cannot use more than X% of wallet. |
| Per-trade max allocation | 10% | Single trade cannot exceed X% of wallet. |
| Max leverage | 5x | Per-asset cap; can be lower per strategy. |
| Max daily loss | 5% wallet / 2% strategy | Halt affected strategy for 24h after hit. |
| Stop-loss | Required | No order submitted without a stop. |
| Take-profit | Optional but recommended | Encourage 1.5–2x R/R. |
| Slippage guard | 1% | Cancel if fill price > 1% from signal price. |
| Liquidity filter | $100k+ 24h volume | Avoid illiquid perps/spot pairs. |
| Max trades per day | 10 | Limit churn and fees. |
| Cooldown | 5 min | Minimum time between new trades in same market. |
| Kill switch | Manual | One button to cancel all orders and flatten per wallet. |

---

## 12. Data Model

```
User
 ├─ wallets: Wallet[]
 ├─ riskProfile
 └─ defaultWalletId

Wallet
 ├─ id, label, address
 ├─ encryptedSecret (API wallet secret)
 ├─ type (main | api | subaccount)
 └─ isPaper

Strategy
 ├─ id, name, description, isTemplate, isActive
 ├─ template (momentum | mean_reversion | funding_arb | delta_neutral | custom)
 ├─ marketType (perp | spot | mixed)
 ├─ markets: string[]
 ├─ agents: string[]
 ├─ llmConfig
 ├─ executionMode (manual | auto_confirm | automatic)
 ├─ schedule (on_demand | interval | event)
 ├─ walletId
 ├─ riskConfig (maxWalletAllocation, maxTradeAllocation, maxLeverage, maxDailyLoss, stopLoss, takeProfit, maxTradesPerDay, cooldownMinutes)
 ├─ mode (paper | live)
 ├─ backtestResult?: BacktestResult
 └─ createdAt, updatedAt

Signal
 ├─ strategyId, walletId, market, action (BUY/SELL/HOLD)
 ├─ confidence, size, leverage, entry, stop, target
 ├─ reasoning, agentReports
 ├─ executionMode
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
 ├─ equityCurve: { date, value }[]
 ├─ trades: Trade[]
 └─ createdAt
```

---

## 13. Page Map

| Route | Purpose |
|---|---|
| `/` | Dashboard: combined & per-wallet portfolio, active strategies |
| `/strategies` | Strategy library and builder |
| `/strategies/:id` | Strategy detail, backtests, activation controls |
| `/scanner` | Hyperliquid market scanner |
| `/signals` | Signal feed and execution queue |
| `/orders` | Open orders and fill history |
| `/positions` | Current positions and PnL per wallet |
| `/backtest` | Backtest lab with statistics at the top |
| `/wallets` | Wallet manager |
| `/memory` | Agent reflection memory browser |
| `/settings` | Risk defaults, API keys, alerts |

---

## 14. Non-Functional Requirements

- **Latency:** Signal generation < 30s per market; order submission < 3s.
- **Uptime:** Backend 99.5% during market hours; retries for API failures.
- **Security:** API wallet keys encrypted at rest; no plaintext keys in logs; no custody of main wallet.
- **Audit:** Every signal, order, override, and strategy change logged immutably.
- **Cost:** Cache Hyperliquid Info API calls; run agents only when needed.
- **Compliance:** Not financial advice disclaimers on every screen; user must acknowledge risks before live mode.

---

## 15. Roadmap

| Phase | Scope | Time |
|---|---|---|
| **V0 — Scaffold & Data** | Vite frontend, Hyperliquid data adapter, market scanner | Week 1 |
| **V1 — Strategy Builder** | Predefined + custom strategies, backtest UI with top statistics | Week 2 |
| **V2 — Multi-Wallet & Paper Trading** | Wallet manager, paper execution, portfolio tracking | Week 3 |
| **V3 — Auto-Trading** | Auto-execution modes, scheduling, risk guardrails | Week 4 |
| **V4 — Live & Polish** | Live signing, alerts, memory/reflection, mobile UI | Week 5 |

---

## 16. Open Questions

1. Do we start with **perps only** or include spot from V0?
2. Which LLM provider gives the best cost/accuracy ratio for Hyperliquid signal generation?
3. How do we source historical candles for backtests — Hyperliquid History API or local cache?
4. Should the app run locally (self-hosted) or as a hosted service?
5. Do we want Telegram/Discord bot alerts or in-app only?
6. Should auto-trading require a second confirmation (2FA / email) for live mode?

---

## 17. Next Steps

1. Scaffold FastAPI backend with Hyperliquid `Info`/`Exchange` clients.
2. Add a `HyperliquidDataAdapter` to `tradingagents/dataflows/`.
3. Implement the strategy library and builder in the frontend.
4. Write perp/spot-specific analyst and risk prompts.
5. Build the backtest interface with statistics at the top.
6. Add wallet management and encrypted secret storage.
7. Implement paper-trading engine and auto-trading scheduler.
8. Run 30-day paper test before enabling live signing.
