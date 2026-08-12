# TradingAgents Web Frontend PRD
## Crypto, NFT & Prediction-Market Command Center

**Author:** Devin (Thomas Berrod session)  
**Date:** 2026-08-12  
**Status:** Draft  
**Related:** `Huaoe/TradingAgents` — Multi-Agent LLM Financial Trading Framework

---

## 1. Executive Summary

Build a web frontend that turns the existing `TradingAgents` Python research framework into a **money-making product layer** for three high-volatility asset classes:

1. **Crypto assets** — spot, perpetuals, and on-chain DEX positions.
2. **NFTs** — collection trading, mint sniping, and rarity-based flipping.
3. **Polymarket** — prediction-market event positions.

The frontend is **not** just a dashboard. It is the **strategy orchestration, execution, and monetization cockpit** for multi-agent LLM signals.

---

## 2. Problem We Are Solving

`TradingAgents` today is a CLI-based research prototype for equities. It produces a textual `BUY / SELL / HOLD` recommendation, has no broker integration, no position sizing, no backtesting harness, and no recurring automation. To generate revenue, we need:

- A product surface that non-engineers can operate.
- Live connectivity to crypto exchanges, NFT marketplaces, and Polymarket.
- A portfolio and risk layer that translates LLM signals into sized, executable orders.
- A backtesting & paper-trading loop that proves alpha before real capital is deployed.
- A monetization layer (subscriptions, signal marketplace, API access).

---

## 3. Goals

| # | Goal | Success Metric |
|---|---|---|
| 1 | Allow users to configure, launch, and monitor multi-agent strategies across crypto, NFT, and Polymarket. | < 3 clicks from login to a running strategy. |
| 2 | Convert LLM signals into executable orders with position sizing, stops, and take-profits. | End-to-end latency from signal → exchange order < 5s for CEX, < 30s for on-chain. |
| 3 | Prove alpha with paper trading & backtests before live capital. | Sharpe, max drawdown, win rate, and benchmark vs. HODL / SPY. |
| 4 | Monetize via subscriptions, signal marketplace, and API. | First paid subscriber within 30 days of V1 launch. |
| 5 | Stay compliant and safe. | Disclaimers, audit logs, risk warnings, no unsupported securities in restricted jurisdictions. |

---

## 4. Target Users

1. **Retail Crypto Traders** — want curated AI signals without writing Python.
2. **NFT Flippers** — need floor/rarity/mint signals and fast listing execution.
3. **Polymarket Predictors** — want event-odds analysis and automated order placement.
4. **Quant/Hedge-Fund Operators** — want to run custom agents, backtest, and white-label.

---

## 5. Product Structure

### 5.1 Core Asset Domains

| Domain | Instruments | Typical Signals | Execution Channels |
|---|---|---|---|
| **Crypto** | Spot, perps, DEX swaps, yield/LP | Long/short, leverage, DCA, funding-rate arb | Binance, Coinbase, Kraken, Hyperliquid, dYdX, 1inch/0x |
| **NFTs** | ERC-721 / ERC-1155 collections & mints | Buy floor, snipe underpriced rares, mint, list/accept bid | OpenSea, Blur, Reservoir, Magic Eden, custom mint contracts |
| **Polymarket** | Binary event outcome shares | Buy Yes/No shares based on probability edge vs market odds | Polymarket CLOB API, Gamma API, on-chain Polygon USDC |

### 5.2 New Analyst Agents Needed

Extend the existing `market`, `social`, `news`, `fundamentals` analysts with crypto-native modules:

- **On-Chain Analyst** — exchange inflows/outflows, whale wallets, smart-money flows, stablecoin issuance.
- **Technical (Crypto) Analyst** — funding rates, liquidation heatmaps, RSI/MACD adapted to 24/7 markets.
- **Macro/Crypto News Analyst** — CoinDesk, The Block, X/Twitter, Reddit, governance proposals.
- **NFT Analyst** — floor price trends, volume, listing velocity, rarity score changes, mint calendar.
- **Polymarket Analyst** — event metadata, order-book depth, implied probability vs. prediction-model probability, resolution source analysis.
- **Risk/Reward Analyst** — volatility, liquidity, smart-contract / oracle / settlement risk.

---

## 6. Key Features

### 6.1 Strategy Builder

- Pick an asset domain (Crypto / NFT / Polymarket).
- Select which agents to include (market, on-chain, macro, NFT, Polymarket, risk).
- Configure LLM provider & model (OpenAI, Anthropic, Google, OpenRouter, local Ollama).
- Set research depth, debate rounds, and max recursion.
- Define signal rules:
  - Minimum confidence threshold.
  - Action types allowed (e.g. only `BUY`/`HOLD` for Polymarket; `LONG`/`SHORT`/`NEUTRAL` for perps).
  - Position sizing method: fixed % of portfolio, Kelly fraction, volatility-targeted, or manual.
  - Stop-loss / take-profit levels.
- Save as a reusable strategy template.

### 6.2 Market Scanner

- Unified screener across all three domains.
- Columns: asset, signal, confidence, expected return, risk score, 24h change, liquidity.
- Filters: domain, signal direction, confidence > X, volatility < Y, market cap/floor range.
- One-click "Investigate" to run the full agent pipeline for that asset.

### 6.3 Signal Feed

- Real-time or on-demand signal cards showing:
  - Asset & market.
  - Agent consensus and dissenting views.
  - Confidence score (0–100%).
  - Recommended action, size, entry, stop, target.
  - Verdict from each analyst team.
- Export signals as JSON / CSV / webhook.

### 6.4 Portfolio & Risk Dashboard

- Aggregate PnL across crypto, NFT, and Polymarket positions.
- Allocation by domain, token, collection, event.
- Risk metrics: exposure, VAR, drawdown, beta to BTC/ETH, correlation heatmap.
- Open orders, pending signals, strategy health.

### 6.5 Execution & Order Management

- **Paper trading mode** by default for every new strategy.
- One-click broker/wallet connection:
  - CEX API keys (read-only first, then trading with IP allowlisting).
  - WalletConnect / RainbowKit for EVM/Solana wallets.
- Order types: market, limit, TWAP, DCA, stop-limit, bracket orders.
- NFT actions: list, bid, accept offer, mint.
- Polymarket actions: buy/sell Yes/No shares, cancel order, redeem after resolution.
- Dry-run preview with estimated slippage, fees, and gas.

### 6.6 Backtest & Alpha Lab

- Select date range, strategy, asset universe.
- Walk-forward simulation using historical on-chain/CEX/market data.
- Outputs: equity curve, drawdown, Sharpe, Sortino, win/loss ratio, alpha vs. benchmark.
- Compare multiple strategies side-by-side.
- Export results for marketing or fundraising.

### 6.7 Reflection & Memory Manager

- After a position closes, feed realized PnL back into `reflect_and_remember()`.
- Visual memory browser: what did the agents learn, what mistakes repeat.
- Allow users to upvote/downvote agent reasoning to fine-tune agent memory.

### 6.8 Monetization Module

| Revenue Stream | Description |
|---|---|
| **Signal Subscriptions** | Tiered access to daily/weekly AI signal feed. |
| **Strategy Marketplace** | Users rent or buy proven strategy templates; creator earns revenue share. |
| **Copy Trading** | Users auto-follow top-performing strategies for a performance fee. |
| **API Keys** | Developers pay per call for signals, backtests, or agent reasoning. |
| **White-Label** | Hedge funds / prop shops license the frontend + backend for their own agents. |

### 6.9 Admin & Compliance

- User auth, roles, team workspaces.
- Audit trail of every signal, order, and override.
- Jurisdiction checks and disclaimer acknowledgments.
- Rate limiting, spending caps, kill switches.

---

## 7. Page Map & User Flows

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Login / Onboard → Connect Wallet / Exchange API → Jurisdiction Disclaimer   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Dashboard (portfolio PnL, open positions, latest signals, risk alerts)      │
└─────────────────────────────────────────────────────────────────────────────┘
       │              │                │                │
       ▼              ▼                ▼                ▼
  Market Scanner  Strategy Builder  Alpha Lab (backtest)  Signal Feed
       │              │                │                │
       └──────────────┴────────────────┴────────────────┘
                              │
                              ▼
              Execution Preview → Paper Trade → Live Trade
                              │
                              ▼
                    Portfolio / Risk Manager
                              │
                              ▼
              Monetization (subscriptions, marketplace, API)
```

### Page Details

| Page | Purpose |
|---|---|
| `/` | Dashboard |
| `/scan` | Market scanner with filters |
| `/strategy/new` | Strategy builder |
| `/strategy/:id` | Strategy detail / edit / run history |
| `/signals` | Signal feed |
| `/backtest` | Backtest configuration & results |
| `/portfolio` | Portfolio, PnL, risk |
| `/orders` | Order history & open orders |
| `/marketplace` | Strategy & signal marketplace |
| `/billing` | Subscriptions, API usage, payouts |
| `/settings` | API keys, wallets, agents, memory |

---

## 8. System Architecture

### 8.1 High-Level Stack

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js 14 + TypeScript + Tailwind + shadcn/ui            │
│  (or React + Vite)                                           │
├─────────────────────────────────────────────────────────────┤
│  TanStack Query / Zustand / RTK for state & server cache  │
│  Recharts / Tremor for charts                                │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Backend (Python)                                    │
│  - Wraps TradingAgents graph                               │
│  - Manages brokers, wallets, backtests, billing            │
├─────────────────────────────────────────────────────────────┤
│  TradingAgents Core (LangGraph)                            │
│  - Crypto/NFT/Polymarket agents                            │
│  - ChromaDB memory                                         │
├─────────────────────────────────────────────────────────────┤
│  Data & Execution Adapters                                 │
│  - CEX APIs, DEX aggregators, wallet SDKs                   │
│  - NFT APIs (Reservoir, OpenSea, Blur)                      │
│  - Polymarket CLOB / Gamma                                  │
│  - On-chain RPC + indexers (Alchemy, Ankr)                  │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Backend Services

- **Strategy Service** — create, version, schedule, and run strategies.
- **Signal Service** — request and cache agent signals, webhooks.
- **Execution Service** — order routing, simulation, and position tracking.
- **Backtest Service** — historical simulation and performance analytics.
- **Portfolio Service** — aggregate positions across exchanges/wallets.
- **Billing Service** — subscriptions, usage metering, payouts.

### 8.3 Data Sources

| Domain | Data / APIs |
|---|---|
| Crypto prices | CoinGecko, CoinMarketCap, Binance, Kraken, Coinbase |
| On-chain | Glassnode, Dune, Alchemy, Ankr, Arkham, Nansen |
| Derivatives | Hyperliquid, dYdX, Binance Futures, Coinglass |
| News & social | X API, Reddit, LunarCrush, CoinDesk RSS |
| NFT | Reservoir, OpenSea API, Blur API, Magic Eden, SimpleHash |
| Polymarket | Polymarket CLOB API, Gamma API, market metadata |

---

## 9. Data Model (MVP)

```
User
 ├─ Strategy[]
 ├─ Portfolio
 ├─ WalletConnection
 └─ Subscription

Strategy
 ├─ assetDomain: CRYPTO | NFT | POLYMARKET
 ├─ selectedAgents: string[]
 ├─ llmConfig: { provider, deep, quick }
 ├─ riskConfig: { maxPositionPct, stopLoss, takeProfit }
 └─ Runs: BacktestRun[] | LiveRun[]

Signal
 ├─ strategyId, asset, action, confidence
 ├─ reasoning, analystReports
 ├─ size, entry, stop, target
 └─ timestamp

Position
 ├─ asset, domain, side, size, entryPrice
 ├─ unrealized/realized PnL, status
 └─ linkedOrders[]

Order
 ├─ signalId, exchange/marketplace, orderType
 ├─ status (pending / filled / cancelled / failed)
 └─ fees, slippage, txHash (on-chain)
```

---

## 10. Security & Risk

### 10.1 Security

- All API keys encrypted at rest (AES-256) and scoped to read-only/trading.
- Wallet signing only via user-controlled wallet (no custody of private keys).
- IP allowlisting for CEX keys.
- 2FA for live trading and withdrawals.
- Webhook signatures and request signing for Polymarket/on-chain.

### 10.2 Operational Risk

- **Default to paper trading** for every new strategy.
- **Spending caps** and daily loss limits per strategy.
- **Kill switch** to halt all live strategies instantly.
- **Slippage guard** — abort if expected execution price deviates > X% from signal.
- **Smart contract risk** — only interact with audited contracts; warn on new/unverified NFT mints.

### 10.3 Compliance

- Clear "not financial advice" disclaimers on every signal and trade preview.
- Jurisdiction gating for restricted users (e.g., US users for Polymarket if restricted).
- Tax-report exports (CSV/1099-like).
- Audit logs retained for 7 years.

---

## 11. Monetization Roadmap

| Phase | Timeframe | Revenue Focus |
|---|---|---|
| **V0 — Alpha** | Weeks 1–2 | Internal paper trading; prove signals on 3 asset classes. |
| **V1 — Signal Feed** | Weeks 3–6 | Launch paid signal subscriptions; free tier with 24h delay. |
| **V2 — Auto-Execution** | Weeks 7–12 | Add CEX/DEX/NFT/Polymarket execution; copy-trading fees. |
| **V3 — Marketplace** | Weeks 13–20 | Strategy templates, API access, white-label deals. |
| **V4 — Institutional** | Weeks 21+ | Custom agent deployments, co-managed funds. |

---

## 12. Success Metrics (KPIs)

- **Product:** MAU, strategy runs per user, signal-to-trade conversion.
- **Financial:** MRR, ARPU, take rate on marketplace, API usage revenue.
- **Trading:** Win rate, Sharpe ratio, alpha vs. benchmark, max drawdown, cost-adjusted returns.
- **Reliability:** Signal latency, order fill rate, uptime, false-positive rate.

---

## 13. Open Questions

1. Which execution venues do we prioritize first? (Hyperliquid + 1inch + Polymarket is a lean EVM stack.)
2. Do we custody user funds or remain non-custodial (wallet + CEX API only)?
3. Which jurisdiction restrictions apply to Polymarket access?
4. Do we build the backend in FastAPI or extend the existing `tradingagents` CLI into a server?
5. How do we source historical NFT/Polymarket data for backtests?

---

## 14. Next Engineering Steps

1. **Backend scaffold** — FastAPI service wrapping `TradingAgentsGraph` with async job queue (Redis + Celery or RQ).
2. **Domain adapters** — implement crypto, NFT, and Polymarket data/execution clients.
3. **New agent prompts** — write crypto/NFT/Polymarket analyst prompts and tool schemas.
4. **Frontend scaffold** — Next.js app with auth, wallet connection, and strategy builder.
5. **Paper trading v0** — simulate trades for all three domains using real market data but fake balances.
6. **Backtest harness** — run a strategy on 90 days of historical data and report Sharpe / drawdown.
7. **Billing integration** — Stripe + usage-based API metering.
