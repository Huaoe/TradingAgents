# Epics — Hyperliquid Trading Agent App

This document breaks the product into high-level epics. Each epic maps to the [Hyperliquid Trading Agent App PRD](./hyperliquid-trading-agent-app-prd.md), rewritten to reuse upstream `TradingAgents` v0.3.1 features.

---

## Progress

| Epic | Status |
|---|---|
| Epic 1 — Hyperliquid Data Adapter | Done |
| Epic 2 — Strategy Library & Builder | Done (merged in PR #4) |
| Epic 3 — Backtesting Lab with Statistics | Done (merged in PR #5) |
| Epic 4 — Multi-Wallet Support | Done (merged in PR #6) |
| Epic 5 — Signal Generation via TradingAgentsGraph | Done (merged in PR #7) |
| Epic 6 — Auto-Trading & Execution Engine | Done (merged in PR #8) |
| Epic 7 — Portfolio, Positions & Risk Management | In Progress |
| Epic 8 — Alerts, Reflection & UI Polish | Not started |

---

## Epic 1: Hyperliquid Data Adapter

Add a Hyperliquid vendor so `TradingAgents` can analyze perp/spot markets with native Hyperliquid data instead of relying on Yahoo spot data.

**Scope**
- New `tradingagents/dataflows/hyperliquid.py` implementing the data functions the agents call:
  - `get_stock_data` (candles)
  - `get_indicators` (OHLCV-derived technicals)
  - `get_funding`, `get_open_interest`, `get_orderbook`, `get_recent_trades`, `get_liquidations`
- Register `hyperliquid` in `dataflows/interface.py` and `default_config.py`.
- Caching layer for Info API calls.
- Symbol normalization bridge (`BTC` <-> `BTC-USD`).

**Definition of Done**
- `TradingAgentsGraph.run(asset_type="crypto", symbol="BTC", data_vendors={..."hyperliquid"})` runs end-to-end using Hyperliquid data.
- Market Scanner in the frontend displays live Hyperliquid prices, 24h change, volume, and funding.
- Candles and funding data are cached locally and refresh in < 5s.

---

## Epic 2: Strategy Library & Builder

Let the user choose from predefined strategy templates or build a custom strategy, and persist it.

**Scope**
- Predefined templates: Momentum Breakout, Mean Reversion, Funding Rate Arb, HYPE Delta Neutral, Custom.
- Strategy form: markets, agents, LLM provider/model (from `model_catalog.py`), risk config, execution mode, schedule, assigned wallet.
- Save, clone, version, delete strategies.
- Frontend `/strategies` and `/strategies/:id`.

**Definition of Done**
- User can create a strategy from a template in < 2 minutes.
- Strategy model is persisted and editable.
- The builder's LLM dropdown is populated from `tradingagents.llm_clients.model_catalog`.

---

## Epic 3: Backtesting Lab with Statistics

Provide a backtest interface that shows headline statistics at the top and detailed analysis below.

**Scope**
- Run a strategy against historical candles (Hyperliquid or yfinance fallback).
- Simulate maker/taker fees, slippage, and funding for perps.
- Compute and display at the top: Total Return, Sharpe, Max Drawdown, Win Rate, Profit Factor, # Trades, Avg Trade, Benchmark Return.
- Equity curve, drawdown chart, monthly heatmap, trade list.
- "Activate as Strategy" after successful backtest.

**Definition of Done**
- Backtest completes in < 30s for 1 year of daily data.
- Statistics cards are visible at the top of `/backtest` without scrolling.
- Results are reproducible for the same strategy + date range.

---

## Epic 4: Multi-Wallet Support

Support multiple Hyperliquid wallets/accounts with encrypted secrets and per-wallet views.

**Scope**
- Wallet CRUD with labels and encrypted API-wallet secrets.
- Wallet switcher in the UI.
- Per-wallet balances, positions, PnL.
- Default wallet per strategy.

**Definition of Done**
- User can add >=2 wallets and switch in < 3 clicks.
- Private keys are never stored in plain text.
- Dashboard shows combined and per-wallet PnL.

---

## Epic 5: Signal Generation via TradingAgentsGraph

Run the upstream multi-agent graph on Hyperliquid markets and expose the typed decisions in the UI.

**Scope**
- FastAPI endpoint that calls `TradingAgentsGraph.run(asset_type="crypto", ...)`.
- Map the upstream `PortfolioDecision` / `TraderProposal` to the app's `Signal` schema.
- Display `SentimentReport` band/score in the signal feed.
- Handle errors gracefully (no data, LLM failure).

**Definition of Done**
- Signal generation < 30s per market.
- UI shows `Buy / Overweight / Hold / Underweight / Sell`, confidence, entry, stop, target, leverage, reasoning.
- 90%+ of runs produce parseable decisions.

---

## Epic 6: Auto-Trading & Execution Engine

Convert signals into Hyperliquid orders and execute them manually, semi-automatically, or fully automatically.

**Scope**
- Manual, auto-confirm, and fully automatic execution modes per strategy.
- Schedule and cooldown guards.
- Order builder for perp/spot market and limit orders.
- Hyperliquid order signing/submission via `hyperliquid-python-sdk`.
- Bracket orders (stop-loss / take-profit).
- Slippage, daily trade limit, and wallet allocation guards.

**Definition of Done**
- Paper-trade execution success rate > 95%.
- Auto-trading respects all risk guardrails.
- User can pause/stop any strategy instantly.

---

## Epic 7: Portfolio, Positions & Risk Management

Track positions, orders, and risk across wallets and strategies.

**Scope**
- Real-time position sync from `clearinghouseState`.
- Open orders list with cancel.
- Per-strategy and per-wallet PnL attribution.
- Risk dashboard: exposure, drawdown, margin, liquidation proximity.
- Kill switch.

**Definition of Done**
- Positions update within 5 seconds of a fill.
- Risk dashboard reflects current margin and exposure.
- Kill switch cancels all open orders and flattens selected positions.

---

## Epic 8: Alerts, Reflection & UI Polish

Notify the user, let the agents learn, and finish the UX.

**Scope**
- In-app, email, Telegram, Discord alerts.
- Feed closed-trade PnL back to `reflect_and_remember()`.
- Memory browser (`/memory`).
- Mobile-responsive UI, dark/light mode, onboarding.
- Not-financial-advice disclaimers and compliance prompts.

**Definition of Done**
- Alerts fire for new signals, fills, stop hits, and risk breaches.
- Reflection loop runs after every closed trade.
- App is usable on a 13" laptop and a phone.
