# Development Plan — Hyperliquid Trading Agent App

This plan orders the [Epics](./EPICS.md) and [User Stories](./USER_STORIES.md) into a development roadmap. It assumes one full-stack engineer (you) working in focused sprints.

---

## Methodology

- **Sprints:** 1 week each.
- **Milestone:** A working, end-to-end demo at the end of every sprint.
- **Definition of Ready:** A user story has clear acceptance criteria and no unresolved dependencies.
- **Definition of Done:** Code is merged, UI is usable, backend endpoints are tested, and the feature works on `localhost`.

---

## Tooling

| Layer | Stack |
|---|---|
| Frontend | Vite + React + TypeScript + Tailwind CSS + Recharts |
| Backend | FastAPI + Python 3.11+ |
| Agent Engine | `TradingAgents` (LangGraph) + custom Hyperliquid analysts |
| Exchange | `hyperliquid-python-sdk` |
| Database | SQLite for local MVP; migrate to PostgreSQL if hosted |
| Secrets | `python-keyring` or file-encrypted vault (no cloud secrets in MVP) |
| Testing | `pytest` (backend), manual UI QA + screenshots |

---

## Sprint Map

### Sprint 0 — Foundation (Days 1–3)
**Goal:** Get the repo and the existing React frontend ready for feature work.

**Stories**
- US-1.1 (partial): Improve market scanner with loading states.
- US-8.3 (partial): Make sidebar responsive.

**Tasks**
1. Decide if the app stays local-only or will need a FastAPI backend now.
2. Add route placeholders for `/strategies`, `/backtest`, `/wallets`.
3. Set up backend folder structure if not already present.
4. Define shared TypeScript types for Strategy, Wallet, BacktestResult.
5. Add `README.md` for `frontend/` with run instructions.

**Milestone:** Frontend skeleton with all planned routes reachable.

---

### Sprint 1 — Hyperliquid Data & Market Foundation
**Goal:** Connect to Hyperliquid and display real market data.

**Epic:** Epic 1

**Stories**
- US-1.1 View live market scanner
- US-1.2 Analyze a single market
- US-1.3 View wallet balance

**Tasks**
1. Install `hyperliquid-python-sdk` in the main project.
2. Create `HyperliquidDataAdapter` in `tradingagents/dataflows/`.
3. Build FastAPI endpoints:
   - `GET /api/markets`
   - `GET /api/markets/{symbol}/analyze` (mock first, real later)
   - `GET /api/wallet/{address}/state`
4. Update frontend scanner to call real endpoints and show loading/error states.
5. Add a simple `.env.example` for `HYPERLIQUID_WALLET`, `HYPERLIQUID_SECRET`, `OPENAI_API_KEY`.

**Milestone:** Market scanner shows live prices from Hyperliquid and can trigger a (mock) analysis.

---

### Sprint 2 — Strategy Library & Builder
**Goal:** Users can create, save, and clone strategies from predefined templates.

**Epic:** Epic 2

**Stories**
- US-2.1 Browse predefined strategy templates
- US-2.2 Create a custom strategy
- US-2.3 Clone and edit a strategy
- US-2.4 Delete a strategy

**Tasks**
1. Design `Strategy` schema and SQLite storage.
2. Seed 5 predefined templates with default parameters.
3. Build `/strategies` page (grid of templates + saved strategies).
4. Build `/strategies/new` and `/strategies/:id` forms with:
   - Market picker
   - Agent picker
   - LLM provider/model pickers
   - Risk config sliders
   - Execution mode selector
   - Schedule selector
5. Persist strategies to backend.

**Milestone:** User can create, save, edit, and delete a strategy from the UI.

---

### Sprint 3 — Backtesting Lab with Statistics
**Goal:** Run historical simulations and display headline stats at the top.

**Epic:** Epic 4

**Stories**
- US-4.1 Run a backtest
- US-4.2 View headline statistics at the top
- US-4.3 Inspect equity curve and trades
- US-4.4 Activate a strategy from a backtest

**Tasks**
1. Build `BacktestService` with fee and slippage model.
2. Cache historical candles locally (Hyperliquid history or yfinance/Coingecko fallback).
3. Compute statistics: Total Return, Sharpe, Max Drawdown, Win Rate, Profit Factor, # Trades, Avg Trade, Benchmark Return.
4. Build `/backtest` page:
   - Strategy + date range + initial balance selector
   - Statistics cards at the top
   - Equity curve + drawdown charts
   - Trade list table
   - "Activate as Paper Strategy" button
5. Wire "Backtest" button from the strategy builder.

**Milestone:** A saved strategy can be backtested and promoted to a paper strategy.

---

### Sprint 4 — Multi-Wallet Support
**Goal:** Support multiple wallets with encrypted secrets and per-wallet views.

**Epic:** Epic 3

**Stories**
- US-3.1 Add a new wallet
- US-3.2 Switch active wallet
- US-3.3 View combined and per-wallet PnL

**Tasks**
1. Create `Wallet` model and `/api/wallets` CRUD.
2. Implement encrypted secret storage (local keyring or AES with a master password).
3. Build `/wallets` page for adding/removing wallets.
4. Add wallet switcher to header/sidebar.
5. Update dashboard, positions, and orders to be wallet-aware.

**Milestone:** User can add two wallets and see per-wallet balances and combined PnL.

---

### Sprint 5 — Signal Generation & Agent Pipeline
**Goal:** Produce real Hyperliquid signals from `TradingAgents`.

**Epic:** Epic 5

**Stories**
- US-5.1 Generate a Hyperliquid-aware signal
- US-5.2 Normalize signal output for execution
- US-5.3 View agent reasoning

**Tasks**
1. Add Hyperliquid-specific analyst prompts to `TradingAgents`.
2. Build `SignalService` that runs the LangGraph pipeline.
3. Normalize signal output to a strict schema.
4. Update `/signals` page to display reasoning and agent reports.
5. Add signal queue for pending/accepted/rejected/executed signals.

**Milestone:** Running a strategy produces a structured signal with agent reasoning in the UI.

---

### Sprint 6 — Auto-Trading & Execution Engine (Paper)
**Goal:** Execute paper trades automatically or with confirmation.

**Epic:** Epic 6

**Stories**
- US-6.1 Set execution mode per strategy
- US-6.2 Paper-trade an order
- US-6.4 Enforce slippage and trade limits

**Tasks**
1. Implement execution modes in the strategy model.
2. Build `ExecutionService` that creates paper trades.
3. Add cooldown, daily trade limit, slippage guard.
4. Wire auto-execution to the signal feed.
5. Add strategy start/pause/stop controls.

**Milestone:** A paper strategy can auto-trade for 24 hours and record simulated PnL.

---

### Sprint 7 — Live Trading & Risk Guardrails
**Goal:** Sign and submit real orders to Hyperliquid safely.

**Epic:** Epic 6 (continued) + Epic 7

**Stories**
- US-6.3 Submit a live order to Hyperliquid
- US-7.3 Kill switch

**Tasks**
1. Implement Hyperliquid order signing with `Exchange` client.
2. Add order preview with slippage, margin, liquidation price.
3. Add live/paper toggle and confirmation modal with risk disclaimer.
4. Implement kill switch: cancel all orders and flatten positions.
5. Add strategy-level live trading guardrails.

**Milestone:** User can run a live strategy on a small wallet balance with full risk controls.

---

### Sprint 8 — Portfolio, Positions & Risk Dashboard
**Goal:** Rich portfolio tracking and risk visibility.

**Epic:** Epic 7

**Stories**
- US-7.1 View open positions
- US-7.2 View open orders and cancel
- US-8.4 Risk disclaimer

**Tasks**
1. Build `/positions` and `/orders` pages.
2. Sync positions from `clearinghouseState` every 5 seconds.
3. Add per-strategy and per-wallet PnL attribution.
4. Build risk dashboard: exposure, margin, drawdown.
5. Add compliance disclaimer modals before live mode.

**Milestone:** User can monitor and manage all open positions and orders.

---

### Sprint 9 — Alerts, Reflection & UI Polish
**Goal:** Make the app usable, reflective, and reliable.

**Epic:** Epic 8

**Stories**
- US-8.1 Receive trade alerts
- US-8.2 Reflect on closed trades
- US-8.3 Mobile-responsive UI

**Tasks**
1. Add in-app notification center.
2. Add optional Telegram/Discord webhook configuration.
3. Implement reflection loop after closed trades.
4. Build `/memory` page.
5. Polish mobile layout, dark mode, onboarding.

**Milestone:** App is usable on mobile, sends alerts, and learns from closed trades.

---

### Sprint 10 — Stabilization & Launch Prep
**Goal:** Harden and release for personal use.

**Stories**
- All acceptance criteria re-verified.
- Performance and error handling review.

**Tasks**
1. End-to-end paper trading for 7 days minimum.
2. Fix bugs and edge cases.
3. Write runbook for `localhost` setup.
4. Optional: package as Electron app or Docker container.
5. Tag a release.

**Milestone:** V1.0 is running locally and ready for real-money testing with small size.

---

## Execution Order Summary

| Sprint | Epic Focus |
|---|---|
| 0 | Repo + frontend skeleton |
| 1 | Epic 1 — Data & market foundation |
| 2 | Epic 2 — Strategy library & builder |
| 3 | Epic 4 — Backtesting lab |
| 4 | Epic 3 — Multi-wallet support |
| 5 | Epic 5 — Signal generation |
| 6 | Epic 6 — Paper auto-trading |
| 7 | Epic 6/7 — Live execution + kill switch |
| 8 | Epic 7 — Portfolio & risk dashboard |
| 9 | Epic 8 — Alerts, reflection, UI polish |
| 10 | Stabilization & release |

---

## Risk & Contingency

| Risk | Mitigation |
|---|---|
| Hyperliquid API changes | Pin SDK version and write adapter behind an interface. |
| LLM costs blow up | Default to cheap models (`gpt-4o-mini`, `claude-haiku`) and cache frequent analyses. |
| Live trading losses | Mandatory 7-day paper run before live; hard stop-loss and position caps. |
| Encrypted secret loss | Document key backup; never store plaintext; test recovery flow. |
| Scope creep | Stick to one epic per sprint; defer NFT/Polymarket to V2. |

---

## How to Use This Plan

1. Pick the next sprint.
2. Move its user stories into your task tracker.
3. At the end of the sprint, run the app on `localhost` and verify the milestone.
4. Update this plan if priorities change (e.g. if live execution is needed sooner than paper).
