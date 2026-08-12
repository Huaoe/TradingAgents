# Hyperliquid Trading Agent App PRD
## Personal AI Trading Terminal for Hyperliquid

**Author:** Devin (Thomas Berrod session)  
**Date:** 2026-08-12  
**Status:** Draft  
**Related:** `Huaoe/TradingAgents` + Hyperliquid Python SDK

---

## 1. Executive Summary

Build a focused web app that extends `TradingAgents` to trade **Hyperliquid** markets using the user's own crypto wallet. The app acts as a personal command center: it runs multi-agent LLM analysis on selected perp/spot markets, translates signals into sized Hyperliquid orders, submits them, and tracks PnL — all under strict user-controlled risk guardrails.

This is the **fastest path to real money** from the TradingAgents framework because Hyperliquid provides:
- Wallet-based authentication (no CEX KYC or API key required).
- A native Python SDK.
- Perpetuals + spot in one venue.
- Low latency and low fees.

---

## 2. Problem Statement

`TradingAgents` currently:
- Generates textual `BUY / SELL / HOLD` signals for equities.
- Has no execution layer, no perp/NFT/crypto data, and no wallet integration.
- Runs from the CLI with no portfolio tracking.

To trade Hyperliquid with it, we need a dedicated product layer that:
1. Feeds Hyperliquid market data into the agents.
2. Parses agent output into executable orders (market/limit, size, leverage, stop, take-profit).
3. Signs and submits orders from the user's wallet.
4. Tracks positions, PnL, and agent performance.
5. Protects the user from blow-ups.

---

## 3. Goals

| # | Goal | Success Metric |
|---|---|---|
| 1 | Run TradingAgents against Hyperliquid perp/spot markets daily or on-demand. | Signal latency < 30s per market. |
| 2 | Convert signals into executable Hyperliquid orders. | Order submission success rate > 95% after paper validation. |
| 3 | Protect capital with hard risk guardrails. | Max drawdown per strategy < user-defined X% (default 10%). |
| 4 | Prove alpha before live trading. | 30-day paper trade beats HODL benchmark. |
| 5 | Be operable by a single user with their own wallet. | < 5 minutes from login to first signal. |

---

## 4. Target User

A single, technically comfortable crypto trader who wants to:
- Automate directional perp/spot strategies on Hyperliquid.
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

### 7.1 Strategy Builder

- Select perp or spot markets (single or watchlist).
- Select which agents to enable.
- Choose LLM provider and models (deep thinker + quick thinker).
- Set risk parameters:
  - Max % of total account per trade.
  - Max leverage per perp.
  - Max daily loss / drawdown.
  - Stop-loss % and take-profit %.
  - Direction filter (long only, short only, both).
- Toggle paper trading vs. live trading.
- Save strategy templates.

### 7.2 Market Scanner

- Grid of Hyperliquid perp and spot markets.
- Columns: last price, 24h change, funding rate, open interest, agent signal, confidence.
- Filters: market type, signal direction, confidence threshold, volatility.
- One-click "Analyze" to run the full TradingAgents graph for that market.

### 7.3 Signal Feed

- Card per market showing:
  - `BUY / SELL / HOLD` with confidence %.
  - Recommended size in USDC and as % of account.
  - Recommended leverage (perps only).
  - Suggested entry, stop-loss, take-profit.
  - Agent reasoning summary.
- User can accept, edit, or reject the signal.

### 7.4 Order Preview & Execution

- On signal accept, show an order preview:
  - Market or limit order.
  - Estimated size, notional, margin, fees (~0.045% taker / 0.015% maker).
  - Slippage estimate from order book.
  - Post-trade account margin and liquidation price (perps).
- One-click "Execute" or "Paper Execute".
- Orders are signed via the Hyperliquid Python SDK using the user's API-wallet private key.

### 7.5 Portfolio & Positions

- Real-time view of open perp/spot positions.
- Unrealized/realized PnL, margin used, available margin.
- Open orders list with cancel buttons.
- Funding payments history.
- Fills history.

### 7.6 Backtest / Paper Trade Lab

- Run a strategy against historical Hyperliquid candle data for a date range.
- Simulate fills with maker/taker fees and slippage.
- Output: equity curve, drawdown, Sharpe, win rate, trades list.
- Paper trade mode: run for N days with fake balance before allowing live.

### 7.7 Reflection & Memory

- After a position closes, feed realized returns back to `reflect_and_remember()`.
- Memory browser: what did the agents learn, which agents are contributing positively.
- User can flag a bad trade to update agent memory.

### 7.8 Alerts

- Web or Telegram/Discord alerts for new signals, executed orders, stop-loss hits, or risk thresholds.

---

## 8. User Flow

```
Onboarding
  ├─ Connect or generate Hyperliquid API wallet
  ├─ Set risk guardrails and paper/live mode
  └─ Fund Hyperliquid account

Dashboard
  ├─ Portfolio snapshot (margin, PnL, open positions)
  ├─ Active strategies
  └─ Latest signals

Market Scanner
  └─ Analyze a market → Signal Feed

Signal Feed
  └─ Accept / Edit / Reject → Order Preview

Order Preview
  └─ Paper or Live Execute → Portfolio

Backtest Lab
  └─ Run simulation → View metrics → Activate as strategy
```

---

## 9. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Next.js + TypeScript + Tailwind Frontend                               │
│  - Dashboard, scanner, strategy builder, signal feed, portfolio          │
├─────────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Python)                                               │
│  - Orchestrates TradingAgents graph                                    │
│  - Wraps Hyperliquid Python SDK for order execution                    │
│  - Manages strategies, positions, backtests, alerts                    │
├─────────────────────────────────────────────────────────────────────────┤
│  TradingAgents Core (LangGraph)                                        │
│  - Hyperliquid data adapters                                           │
│  - New perp/spot analyst and risk agents                               │
│  - Memory (ChromaDB) and reflection                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Hyperliquid Network                                                   │
│  - Info API (read-only, no auth)                                       │
│  - Exchange API (signed orders via user wallet)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Backend Services

| Service | Responsibility |
|---|---|
| **Strategy Service** | Create, schedule, and version strategies. |
| **Signal Service** | Run the TradingAgents graph and normalize output. |
| **Execution Service** | Build, sign, and submit Hyperliquid orders; track fills. |
| **Data Service** | Fetch candles, order book, funding, OI from Hyperliquid Info API; cache locally. |
| **Portfolio Service** | Sync `clearinghouseState` and open orders; compute PnL. |
| **Backtest Service** | Historical simulation with fee/slippage model. |
| **Alert Service** | Webhooks / Telegram / Discord notifications. |

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

- User generates an **API wallet** from the Hyperliquid UI.
- App stores only the API-wallet private key, never the main wallet seed.
- Private key is encrypted at rest (e.g. AWS KMS / HashiCorp Vault / 1Password-style local encryption).
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
| Max account allocation | 10% per trade | Reject signals that exceed this. |
| Max leverage | 5x | Per-asset cap; can be lower. |
| Max daily loss | 5% | Halt strategy for 24h after hit. |
| Stop-loss | Required | No order submitted without a stop. |
| Take-profit | Optional but recommended | Encourage 1.5–2x R/R. |
| Slippage guard | 1% | Cancel if fill price > 1% from signal price. |
| Liquidity filter | $100k+ 24h volume | Avoid illiquid perps/spot pairs. |
| Kill switch | Manual | One button to cancel all orders and flatten. |

---

## 12. Data Model (MVP)

```
User
 ├─ walletAddress
 ├─ apiWalletEncryptedKey
 └─ riskProfile

Strategy
 ├─ name, marketType (perp|spot)
 ├─ markets: string[]
 ├─ agents: string[]
 ├─ llmConfig
 ├─ riskConfig (maxAllocation, maxLeverage, stopLoss, takeProfit)
 ├─ mode (paper|live)
 └─ createdAt, updatedAt

Signal
 ├─ strategyId, market, action (BUY/SELL/HOLD)
 ├─ confidence, size, leverage, entry, stop, target
 ├─ reasoning, agentReports
 └─ timestamp

Order
 ├─ signalId
 ├─ hyperliquidOrderId (oid)
 ├─ market, side, size, price, orderType
 ├─ status (pending / filled / partial / cancelled / failed)
 ├─ fillPrice, fee, slippage
 └─ txTimestamp

Position
 ├─ market, side, size, entryPrice
 ├─ unrealizedPnl, realizedPnl
 ├─ liquidationPrice (perps)
 ├─ leverage, marginUsed
 └─ lastUpdated

Trade
 ├─ openOrderId, closeOrderId
 ├─ pnl, returnPct, duration
 ├─ strategyId, market
 └─ closedAt
```

---

## 13. Page Map

| Route | Purpose |
|---|---|
| `/` | Dashboard: portfolio, active strategies, recent signals |
| `/scanner` | Hyperliquid market scanner |
| `/strategy/new` | Strategy builder |
| `/strategy/:id` | Strategy detail, run history, PnL |
| `/signals` | Signal feed with accept/edit/reject |
| `/orders` | Open orders and fill history |
| `/positions` | Current positions and PnL |
| `/backtest` | Paper trade / backtest lab |
| `/memory` | Agent reflection memory browser |
| `/settings` | Wallet, risk profile, API keys, alerts |

---

## 14. Non-Functional Requirements

- **Latency:** Signal generation < 30s per market; order submission < 3s.
- **Uptime:** Backend 99.5% during market hours; use retries for API failures.
- **Security:** API wallet key encrypted at rest; no plaintext keys in logs; no custody of main wallet.
- **Audit:** Every signal, order, and override logged immutably.
- **Cost:** Cache Hyperliquid Info API calls aggressively; run agents only when needed or on a schedule.
- **Compliance:** Not financial advice disclaimers on every screen; user must acknowledge risks before live mode.

---

## 15. Roadmap

| Phase | Scope | Time |
|---|---|---|
| **V0 — Data + Signals** | Hyperliquid data adapter, market scanner, perp/spot signal generation | Week 1 |
| **V1 — Paper Trading** | Paper execution loop, backtest lab, portfolio dashboard | Week 2–3 |
| **V2 — Live Trading** | API wallet signing, risk guardrails, live order submission | Week 4–5 |
| **V3 — Automation** | Scheduled strategy runs, alerts, memory reflection | Week 6–7 |
| **V4 — Polish** | Mobile UI, advanced analytics, strategy marketplace (optional) | Week 8+ |

---

## 16. Open Questions

1. Do we start with **perps only** or include spot from V0?
2. Which LLM provider gives the best cost/accuracy ratio for Hyperliquid signal generation?
3. How do we source historical candles for backtests — Hyperliquid History API or local cache?
4. Should the app run locally (self-hosted) or as a hosted service?
5. Do we want Telegram/Discord bot alerts or in-app only?

---

## 17. Next Steps

1. Scaffold FastAPI backend with Hyperliquid `Info`/`Exchange` clients.
2. Add a `HyperliquidDataAdapter` to `tradingagents/dataflows/`.
3. Write perp/spot-specific analyst and risk prompts.
4. Build a minimal Next.js dashboard with wallet connect and market scanner.
5. Implement paper trading loop and PnL tracking.
6. Run 30-day paper test before enabling live signing.
