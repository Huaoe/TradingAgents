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
| Epic 7 — Portfolio, Positions & Risk Management | Done (merged in PR #9) |
| Epic 8 — Alerts, Reflection & UI Polish | Done (merged in PR #10) |

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

---

# Phase 2 — Post-MVP Hardening & Production Readiness

The following epics are derived from the code review of the current app. They focus on packaging, correctness, live/backtest consistency, real-time PnL, security, frontend polish, and testing.

## Progress

> Phase 2 was delivered in the stabilization/hardening commit on `main` (`abfb94b`). Most epics are complete; the few remaining gaps are called out below.

| Epic | Status |
|---|---|
| Epic 9 — Packaging, Deployment & Developer Experience | Done |
| Epic 10 — Backtest Correctness & Live/Backtest Consistency | Done (Sharpe still uses equity-curve pct-change, clamped; can be refined to returns-on-capital) |
| Epic 11 — Real-Time Portfolio & PnL | Done |
| Epic 12 — Security & Risk Hardening | Done |
| Epic 13 — Frontend Polish & Real Data | Done |
| Epic 14 — Testing & Observability | Partial (backend smoke/unit tests + CI done; `/api/health` does not yet probe DB or Hyperliquid; frontend component tests not added) |

## Epic 9: Packaging, Deployment & Developer Experience

Make the app installable, runnable, and deployable by others.

**Scope**
- Create `app/pyproject.toml` (or `app/requirements.txt`) listing the app-only dependencies: `fastapi`, `uvicorn`, `pydantic`, `hyperliquid-python-api`, `cryptography`, `numpy`, `pandas`, and the `tradingagents` engine package.
- Fix `app/Dockerfile.web` and `app/docker-compose.web.yml` build context, copy paths, and final command.
- Update `docs/RUNBOOK.md` to the current directory layout and dependency install steps.
- Add `ruff`, `pytest`, and `httpx` dev dependencies and a GitHub Actions job for the app.

**Definition of Done**
- `docker compose -f app/docker-compose.web.yml up --build` works from a clean clone.
- `cd app && python -m backend.main` and `cd app/frontend && npm run dev` start the app following the runbook.
- CI runs `ruff check app/backend`, `pytest app/backend/tests`, and `npm run build` in `app/frontend`.

## Epic 10: Backtest Correctness & Live/Backtest Consistency

Ensure backtests are realistic and live signals match the logic that was backtested.

**Scope**
- Remove look-ahead bias: shift all bar-derived indicators by one bar in `_prepare_candles` or execute entries/exits at the next bar's open.
- Unify template-specific rules between `app/backend/services/backtest.py` and `app/backend/services/signal_engine.py`, or disable live execution for templates whose live logic is not implemented.
- Replace the equity-curve Sharpe calculation with returns on deployed capital or log returns, and clamp extreme values.
- Add synthetic-data regression tests for every strategy template.

**Definition of Done**
- A deterministic backtest produces the same result across runs.
- Running the same strategy in backtest and live over an identical recent period yields the same directional signals within tolerance.
- Sharpe and drawdown numbers are in a realistic, stable range.

## Epic 11: Real-Time Portfolio & PnL

Make the dashboard and positions reflect live market prices.

**Scope**
- Add a background job that refreshes `markPrice` and `pnl` for open positions using `HyperliquidClient.get_market`.
- Update `app/backend/services/portfolio_engine.py` to use live mark prices for `unrealizedPnl` and `totalValue`.
- Store and plot real portfolio equity history for the Dashboard.
- Show per-position unrealized PnL and distance to liquidation.

**Definition of Done**
- Dashboard PnL updates every 5–10 seconds without a page reload.
- Positions page shows current mark price and live unrealized PnL.
- The Dashboard equity curve is real, not mock data.

## Epic 12: Security & Risk Hardening

Protect secrets and prevent accidental real trading.

**Scope**
- Generate a unique salt per wallet (stored alongside `encrypted_key`) or use the OS keyring for private-key encryption.
- Remove the "show encrypted key" eye icon from the Wallets page.
- Add an explicit two-step live-trading confirmation modal before any live order.
- Validate `llmProvider`/`llmModel` against `tradingagents.llm_clients.model_catalog` when saving a strategy.
- Replace broad `except Exception` handlers in `app/backend/main.py` with targeted error handling and generic frontend messages.
- Add input validation for `symbol`, `limit`, date ranges, and order sizes.

**Definition of Done**
- Wallet secrets are encrypted with a per-wallet salt or keyring-backed storage.
- Live order submission requires a clear confirmation in the UI.
- No stack traces or raw exceptions are returned to the frontend.

## Epic 13: Frontend Polish & Real Data

Replace mock data and improve the user experience.

**Scope**
- Remove `app/frontend/src/data/mockData.ts` and all `mockAccount` / `equityData` fallbacks from `api.ts` and `Dashboard.tsx`.
- Add loading skeletons, error boundaries, and retry logic for all pages.
- Fix the `WalletContext` fast-refresh warning by splitting the provider and hook into separate files.
- Add percent/value labels and validation to `StrategyEditor` funding, allocation, and threshold fields.
- Improve mobile responsiveness for tables and the sidebar.

**Definition of Done**
- Dashboard and all pages display real data or explicit empty/error states.
- `npm run lint` and `npm run build` produce no warnings.
- The app is usable without horizontal scrolling on a 375px-wide device.

## Epic 14: Testing & Observability

Add confidence through tests, logs, and monitoring.

**Scope**
- Add FastAPI endpoint smoke tests using `TestClient`.
- Add unit tests for `backtest.py`, `signal_engine.py`, `execution_engine.py`, and `portfolio_engine.py` with synthetic market data.
- Add frontend component tests for `Backtest`, `StrategyEditor`, and `Signals`.
- Add structured logging and expose dependency health in `/api/health`.
- Track metrics: LLM spend per signal, signal generation latency, paper/live execution success rate.

**Definition of Done**
- App backend has >70% line coverage on service modules.
- CI passes on pull requests.
- `/api/health` reports database and Hyperliquid Info API connectivity.
