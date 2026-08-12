# Epics — Hyperliquid Trading Agent App

This document breaks the product into high-level epics. Each epic maps to the [Hyperliquid Trading Agent App PRD](./hyperliquid-trading-agent-app-prd.md).

---

## Epic 1: Hyperliquid Data & Market Foundation

Build the connection to Hyperliquid so the app can read market data, wallets, and positions.

**Scope**
- Hyperliquid `Info` and `Exchange` SDK integration.
- Fetch perp/spot prices, candles, order book, funding, open interest, liquidations.
- Local caching layer for candles and market metadata.
- Wallet balance and `clearinghouseState` sync.

**Definition of Done**
- Backend endpoints return live market data for BTC, ETH, SOL and at least 5 spot pairs.
- Market data latency < 5 seconds from Hyperliquid.
- Frontend Market Scanner renders live mid prices, 24h change, and funding.

---

## Epic 2: Strategy Library & Builder

Let the user choose from predefined strategy templates or build a custom strategy from scratch.

**Scope**
- Predefined templates: Momentum Breakout, Mean Reversion, Funding Rate Arb, HYPE Delta Neutral, Custom.
- Strategy parameter form: markets, agents, LLM config, risk config, execution mode, schedule.
- Save, clone, version, and delete strategies.
- Template marketplace seed (local JSON).

**Definition of Done**
- User can create a strategy from a template in < 2 minutes.
- All parameters are persisted and editable.
- Frontend `/strategies` page lists templates and saved strategies.

---

## Epic 3: Multi-Wallet Support

Support multiple Hyperliquid wallets/accounts with per-wallet allocation and security.

**Scope**
- Add, label, and remove wallets.
- Encrypted storage of API-wallet secrets.
- Per-wallet balances, positions, and PnL.
- Assign a default wallet per strategy.

**Definition of Done**
- User can add ≥2 wallets and switch between them in < 3 clicks.
- Private keys are never stored in plain text.
- Dashboard shows combined and per-wallet PnL.

---

## Epic 4: Backtesting Lab with Statistics

Provide a backtest interface that shows headline statistics at the top and detailed analysis below.

**Scope**
- Run a strategy against historical candles.
- Compute: Total Return, Sharpe, Max Drawdown, Win Rate, Profit Factor, # Trades, Avg Trade, Benchmark Return.
- Display statistics header cards at the top of the page.
- Equity curve, drawdown chart, trade list, monthly returns.
- Walk-forward / out-of-sample selector.
- "Activate as Strategy" from a successful backtest.

**Definition of Done**
- Backtest completes in < 30s for 1 year of daily data.
- Statistics cards are visible without scrolling.
- Results are reproducible for the same strategy + date range.

---

## Epic 5: Signal Generation & Agent Pipeline

Run the TradingAgents multi-agent graph on Hyperliquid markets and produce normalized signals.

**Scope**
- Hyperliquid data adapter inside `TradingAgents`.
- New perp/spot analysts and prompts.
- Debate + risk manager flow.
- Signal output normalization: action, confidence, size, entry, stop, target, leverage, reasoning.
- Feed signals into the frontend Signal Feed.

**Definition of Done**
- Signal generation < 30s per market.
- Signal schema matches the execution engine input.
- 90%+ of signals are parseable without manual intervention.

---

## Epic 6: Auto-Trading & Execution Engine

Convert signals into orders and execute them automatically or with user confirmation.

**Scope**
- Manual, auto-confirm, and fully automatic execution modes.
- Scheduled and event-based strategy runs.
- Order builder for perp/spot market and limit orders.
- Hyperliquid order signing and submission.
- Bracket orders (stop-loss / take-profit).
- Trade cooldown, daily trade limit, slippage guard.
- Activity log.

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
- Reflection: feed closed-trade PnL back to `reflect_and_remember()`.
- Memory browser.
- Mobile-responsive UI, dark/light mode, onboarding flow.
- Not-financial-advice disclaimers and compliance prompts.

**Definition of Done**
- Alerts fire for new signals, fills, stop hits, and risk breaches.
- Reflection loop runs after every closed trade.
- App is usable on a 13" laptop and a phone.
