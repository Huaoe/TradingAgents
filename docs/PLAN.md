# Development Plan — Hyperliquid Trading Agent App

This plan orders the [Epics](./EPICS.md) and [User Stories](./USER_STORIES.md) into a development roadmap. It is aligned with upstream `TradingAgents` v0.3.1 so we reuse crypto asset mode, structured schemas, multi-provider LLM clients, and the existing test/CI setup.

---

## Methodology

- **Sprints:** 1 week each.
- **Milestone:** A working, end-to-end demo at the end of every sprint.
- **Definition of Ready:** A user story has clear acceptance criteria and no unresolved dependencies.
- **Definition of Done:** Code is merged, UI is usable, backend endpoints are tested, and the feature works on `localhost`.

---

## Progress

| Sprint | Epic | Status |
|---|---|---|
| Sprint 0 — Repo Alignment | Setup | Done |
| Sprint 1 — Hyperliquid Data Adapter | Epic 1 | Done (live market scanner + FastAPI backend merged in PR #2) |
| Sprint 2 — Strategy Library & Builder | Epic 2 | Done (merged in PR #4) |
| Sprint 3 — Backtesting Lab with Statistics | Epic 3 | Done (merged in PR #5) |
| Sprint 4 — Multi-Wallet Support | Epic 4 | Done (merged in PR #6) |
| Sprint 5 — Signal Generation via TradingAgentsGraph | Epic 5 | Done (merged in PR #7) |
| Sprint 6 — Auto-Trading & Execution Engine (Paper) | Epic 6 | Done (merged in PR #8) |
| Sprint 7 — Live Trading & Risk Guardrails | Epic 7 | Done (merged in PR #9) |
| Sprint 8 — Portfolio, Positions & Risk Dashboard | Epic 7 | Done |
| Sprint 9 — Alerts, Reflection & UI Polish | Epic 8 | Done (merged in PR #10) |
| Sprint 10 — Stabilization & Launch Prep | — | Done (merged in PR #11) |
| Sprint 11 — Phase 2 Hardening | Epics 9–14 | Done (merged in PR #12; Epic 14 partial — `/api/health` does not yet probe DB/Hyperliquid and frontend component tests are not added) |
| Sprint 12 — Execution Realism & Strategy Research | Epics 15–16 | Done (merged in PR #14, #15, #16, #17) |
| Sprint 13 — Security Remediation | Epic 17 | Deferred by the owner — the app runs on a single local machine, so exposure is judged acceptable. Still blocks any hosted or shared deployment. |
| Sprint 14 — Live-Trading Readiness | Epic 18 | Done except the testnet soak (merged in PR #19; measured live fills/fees/funding, paper/live separation, read-only reconciliation, real health probes) |
| Sprint 15 — Research Depth & Frontend Debt | Epics 19–20 | Not started |
| Sprint 16 — Execution Parity & Controls | Epic 21 | In progress |

---

## Current State (2026-08-19)

`main` is at `696bb9f`. 85 backend tests pass; `ruff check`, `npm run lint`, `tsc --noEmit` and `npm run build` are clean.

**What works end to end:** market scanner, strategy library, backtest lab, multi-wallet storage, signal generation through `TradingAgentsGraph`, paper execution, portfolio/positions, alerts, and the Strategy Finder.

**What Sprint 12 changed, and why it matters for expectations:**

- Backtest costs are now Hyperliquid-calibrated (maker `0.00015` / taker `0.00045`, measured book slippage `~0.00005`, hourly funding on current notional with the 4%/hour clamp). Before this, fees alone consumed ~29% of the account on the churniest template, so *every* result was negative for accounting reasons rather than signal reasons.
- Churn controls (`minHoldBars`, `cooldownBars`, `exitHysteresis`) and stop-loss / take-profit / trailing-stop are simulated, so a template's own trade management is finally being tested.
- The Strategy Finder does anchored walk-forward selection over a parameter grid and reports a Deflated Sharpe Ratio, an in-sample-vs-out-of-sample rank correlation, and per-regime breakdowns.
- **The honest read of the current results:** on BTC 1h over the last 60 days, walk-forward selection compounds to **+0.16%** against **+7.06%** buy-and-hold over the same test windows, and the winner's DSR is **0.29 across 128 trials** — i.e. not distinguishable from luck. No template in the library currently has demonstrated out-of-sample edge on this asset and period. Treat the library as a set of hypotheses to be tested, not a set of strategies to be run.

**What Sprint 14 changed (PR #19):** live PnL, fees and funding are read back from `userFills` and the funding history instead of being assumed from a fee constant; paper and live balances are separated so a live fill no longer moves the simulated balance; a read-only reconciler compares local live positions against `clearinghouseState` and reports divergences instead of silently "fixing" them; `/api/health` probes every SQLite store and the Info API. Not yet true: none of this has been exercised against a real live order, and the net-PnL formula assumes Hyperliquid's `closedPnl` is gross of fees (recorded as `netPnlBasis` in the order meta) — the first real live close must be checked against the Hyperliquid UI.

**The parity gap Sprint 16 addresses:** `stopLossPct`, `takeProfitPct` and `trailingStopPct` were honoured only by the backtest engine and the Strategy Finder. Nothing in the paper or live execution path placed or monitored them, so every backtest number depended on trade management that real trading never applied. In the same area, the strategy's `riskConfig` never reached execution (it was not written into the signal's `meta`), so risk guardrails ran on defaults, and there was no kill switch and no way to cancel a resting exchange order.

**Known open risks:** the deferred security findings (details in Epic 17) — the SPA catch-all in `app/backend/main.py` serves arbitrary files, `GET /api/wallets` returns `encryptedKey`, seven runtime `.db` files (including `wallets.db`) are tracked in git, and the API has no authentication. These are survivable only because the app runs on localhost with the port unpublished; they are blocking for any hosted, shared or port-exposed run, and the key in the committed `wallets.db` should be treated as public. Beyond security: execution is market-order-only (so the maker-cost results that make the funding templates look viable are not reachable live), and there is no scheduler, so signals and executions are manual — the app is a trading console, not yet an autonomous agent.

---

## Next Up — Prioritised

| # | Work | Why now |
|---|---|---|
| 1 | Epic 21 — Execution parity & controls | Protective exits existed only in the simulator, so live and paper trading did not implement the strategies that were backtested. Also adds the missing kill switch and order cancel. In progress. |
| 2 | Epic 22 — Limit orders & scheduling | Market-only execution makes the ~3 bps maker results unreachable, and an unused `schedule`/`executionMode` means nothing trades unattended. Live automation additionally needs a session key-unlock design, since signing requires the master password. |
| 3 | Epic 19 — Research depth | The library has no demonstrated edge yet; the Strategy Finder needs persisted runs, purged cross-validation and cross-asset sweeps to search for one honestly. |
| 4 | Epic 18 leftovers | One controlled testnet or small-size live round trip to verify fill shape, partial fills, rejected orders, the `closedPnl` fee assumption and the funding sign. Needs a funded wallet and the master password. |
| 5 | Epic 20 — Frontend & observability debt | Two chart libraries ship in the bundle and there are no frontend component tests. |
| — | Epic 17 — Security remediation | Deferred by the owner for local-only use. Promote to #1 the moment the app is exposed beyond localhost. |

---

## Tooling

| Layer | Stack |
|---|---|
| Frontend | Vite + React + TypeScript + Tailwind CSS + Recharts (equity/drawdown) + Lightweight Charts (candlesticks) |
| Backend | FastAPI + Python 3.11+ |
| Agent Engine | `TradingAgents` (upstream `TradingAgentsGraph`, `AssetType.CRYPTO`, structured schemas) |
| Exchange | `hyperliquid-python-sdk` |
| Database | SQLite for local MVP; migrate to PostgreSQL if hosted |
| Secrets | `python-keyring` or file-encrypted vault (no cloud secrets in MVP) |
| Testing | `pytest` (backend), manual UI QA + screenshots |

---

## Sprint Map

### Sprint 0 — Repo Alignment (Days 1–2)
**Goal:** Understand and wire into the new upstream capabilities.

**Stories**
- Read `cli/models.py`, `cli/utils.py`, `tradingagents/agents/schemas.py`, `tradingagents/llm_clients/model_catalog.py`, `dataflows/interface.py`.
- Verify `TradingAgentsGraph` can run on a crypto symbol (`BTC-USD`) in `localhost`.

**Tasks**
1. Run `pytest` to confirm the upstream test suite passes.
2. Run a CLI analysis for `BTC-USD` and inspect the report.
3. Add route placeholders for `/strategies`, `/backtest`, `/wallets` in the existing React frontend.
4. Update shared TypeScript types (`Strategy`, `Wallet`, `BacktestResult`, `Signal`) to match upstream `PortfolioDecision` / `TraderProposal`.

**Milestone:** Upstream `TradingAgents` runs for crypto symbols; frontend routes exist.

---

### Sprint 1 — Hyperliquid Data Adapter
**Goal:** Add a `hyperliquid` vendor so the graph can analyze perp/spot markets with native Hyperliquid data.

**Epic:** Epic 1

**Stories**
- US-1.1 View live market scanner
- US-1.2 Analyze a single market with Hyperliquid data
- US-1.3 Register Hyperliquid as a data vendor

**Tasks**
1. Install `hyperliquid-python-sdk`.
2. Create `tradingagents/dataflows/hyperliquid.py`:
   - `get_stock_data(symbol, start, end)` → candles
   - `get_indicators(...)` → OHLCV-derived technicals
   - `get_funding(symbol)`, `get_open_interest(symbol)`, `get_orderbook(symbol)`, `get_recent_trades(symbol)`, `get_liquidations(symbol)`
3. Register `hyperliquid` in `dataflows/interface.py` and `default_config.py`.
4. Build FastAPI endpoints:
   - `GET /api/markets`
   - `GET /api/markets/{symbol}/fundamentals` (placeholder or skip for crypto)
   - `POST /api/analyze` → runs `TradingAgentsGraph` in crypto mode and returns `PortfolioDecision`/`TraderProposal`/`SentimentReport`
5. Update frontend scanner to show live Hyperliquid prices, 24h, volume, funding.
6. Cache Info API calls locally.

**Milestone:** `/scanner` shows live Hyperliquid data; "Analyze" triggers `TradingAgentsGraph` and returns a typed decision.

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
2. Seed 5 templates with default parameters.
3. Build `/strategies` page (grid of templates + saved strategies).
4. Build `/strategies/new` and `/strategies/:id` forms:
   - Market picker
   - Agent picker (Market, Funding/OI, Sentiment, News)
   - LLM provider/model picker (driven by `model_catalog.py`)
   - Risk config sliders
   - Execution mode selector
   - Schedule selector
   - Wallet selector
5. Persist strategies to backend.

**Milestone:** User can create, save, edit, and delete a strategy from the UI.

---

### Sprint 3 — Backtesting Lab with Statistics
**Goal:** Run historical simulations and display headline stats at the top.

**Epic:** Epic 3

**Stories**
- US-3.1 Run a backtest
- US-3.2 View headline statistics at the top
- US-3.3 Inspect equity curve and trades
- US-3.4 Activate a strategy from a backtest

**Tasks**
1. Build `BacktestService` with fee and slippage model; use Hyperliquid candles or yfinance fallback.
2. Compute statistics: Total Return, Sharpe, Max Drawdown, Win Rate, Profit Factor, # Trades, Avg Trade, Benchmark Return.
3. Build `/backtest` page:
   - Strategy + date range + initial balance selector
   - Statistics cards at the top
   - Equity curve + drawdown charts
   - Trade list table
   - "Activate as Paper Strategy" button
4. Wire "Backtest" button from the strategy builder.

**Milestone:** A saved strategy can be backtested and promoted to a paper strategy.

---

### Sprint 4 — Multi-Wallet Support
**Goal:** Support multiple wallets with encrypted secrets and per-wallet views.

**Epic:** Epic 4

**Stories**
- US-4.1 Add a new wallet
- US-4.2 Switch active wallet
- US-4.3 View combined and per-wallet PnL

**Tasks**
1. Create `Wallet` model and `/api/wallets` CRUD.
2. Implement encrypted secret storage (local keyring or AES with master password).
3. Build `/wallets` page for adding/removing wallets.
4. Add wallet switcher to header/sidebar.
5. Update dashboard, positions, and orders to be wallet-aware.

**Milestone:** User can add two wallets and see per-wallet balances and combined PnL.

---

### Sprint 5 — Signal Generation via TradingAgentsGraph
**Goal:** Run the upstream graph for crypto and expose typed decisions in the UI.

**Epic:** Epic 5

**Stories**
- US-5.1 Run the upstream graph for crypto
- US-5.2 Display structured signal output
- US-5.3 Normalize signal for execution

**Tasks**
1. Create `/api/signals` endpoint that calls `TradingAgentsGraph.run(asset_type="crypto", ...)`.
2. Map `PortfolioDecision` + `TraderProposal` + `SentimentReport` to the frontend `Signal` type.
3. Handle `AssetType.CRYPTO` filtering (fundamentals excluded).
4. Update `/signals` page to display reasoning, agent reports, and sentiment.
5. Add signal queue for pending/accepted/rejected/executed.

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
2. Build `ExecutionService` that creates paper trades using live mid prices.
3. Add cooldown, daily trade limit, slippage guard, wallet allocation check.
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
4. Implement kill switch: cancel all orders and flatten positions for selected wallet.
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

### Sprint 12 — Execution Realism & Strategy Research *(Done)*
**Goal:** Make backtests reflect Hyperliquid's actual conditions, and add a defensible way to compare strategies.

**Epics:** Epic 15, Epic 16

**Delivered**
1. Maker/taker fees pulled from the wallet's effective `userFees`, configurable slippage, hourly funding on current notional with the 4%/hour clamp (PR #14).
2. Churn controls and simulated stop-loss / take-profit / trailing-stop (PR #14).
3. Lightweight Charts candlesticks with volume pane and trade markers (PR #15).
4. Safe live configuration: `LIVE_TRADING` gate, per-wallet gate, mainnet/testnet resolution, leverage set before live orders (PR #16).
5. Strategy Finder: anchored walk-forward search, Deflated Sharpe Ratio, rank correlation, regime breakdowns (PR #17).

**Milestone:** A backtest's costs match Hyperliquid within a basis point or two, and a strategy comparison states whether its winner is distinguishable from noise.

---

### Sprint 13 — Security Remediation *(Deferred — local-only use)*
**Goal:** Make the app safe to run against a mainnet wallet.

**Epic:** Epic 17

**Tasks**
1. Constrain the SPA catch-all to files resolved inside `FRONTEND_DIST`, and reject anything that escapes it.
2. Stop returning `encryptedKey` (and `salt`) from any wallet endpoint; keep them server-side only.
3. Untrack all seven runtime `.db` files, add them to `.gitignore`, and treat any key ever stored in the committed `wallets.db` as compromised — rotate it.
4. Add a local auth gate (bearer token from env, or bind to loopback by default) so mutating endpoints are not open to anything that can reach the port.
5. Default the container to `127.0.0.1` publishing, and require an explicit opt-in to expose it.

**Milestone:** A path-traversal attempt returns 404, no endpoint returns key material, and an unauthenticated caller cannot place an order.

---

### Sprint 14 — Live-Trading Readiness *(Done except task 4)*
**Goal:** Make a live run's reported state match the exchange's actual state.

**Epic:** Epic 18

**Tasks**
1. Reconcile internal positions/fills against `clearinghouseState` and `userFills` on a timer; surface divergence as an alert.
2. Complete live accounting: record actual fill price, fee and funding paid, rather than assumed values.
3. Make `/api/health` probe SQLite and the Hyperliquid Info API rather than returning a static `ok`.
4. Test the kill switch against testnet, including partial-fill and rejected-order paths.
5. Declare `yfinance` in `app/pyproject.toml` (it is imported by the backtest fallback but undeclared).

**Milestone:** A testnet run for 24 hours ends with internal state and exchange state in agreement, with any divergence explained.

---

### Sprint 15 — Research Depth & Frontend Debt
**Goal:** Search for a real edge, and pay down UI/observability debt.

**Epics:** Epic 19, Epic 20

**Tasks**
1. Persist search runs so results are comparable over time instead of re-derived per session.
2. Add purged/embargoed cross-validation alongside the anchored walk-forward, so overlapping-label leakage is bounded.
3. Sweep across assets and intervals, and report which templates survive out of sample in more than one market.
4. Make regime conditioning actionable: allow a strategy to be enabled only in the regimes where it survived.
5. Consolidate charts onto one library and add frontend component tests for `Backtest`, `StrategyFinder` and `StrategyEditor`.

**Milestone:** Either a template with out-of-sample survival across at least two assets, or a documented conclusion that the current library has no edge worth trading.

---

### Sprint 16 — Execution Parity & Controls *(In progress)*
**Goal:** Make live and paper trading implement the strategy that was backtested, and give the operator a way to stop everything.

**Epic:** Epic 21

**Tasks**
1. Write the strategy's effective `riskConfig` into the signal's `meta` so protective levels and risk guardrails use what the user configured instead of defaults.
2. Persist protective levels on the position from the actual fill price, and record the exit reason and both the trigger level and the realised fill on a protective close.
3. Enforce protective exits in paper mode from the existing re-mark loop, mirroring the backtest's precedence (stop/trailing before take-profit, nearest candidate first).
4. Enforce them in live mode exchange-side, with reduce-only trigger orders placed after the entry fill and cancelled on close, since the signing key is not held outside a request.
5. Add resting-order listing, single-order cancel, and a kill switch that cancels, flattens and turns the wallet's live gate off.

**Milestone:** A paper position with a stop closes itself at the stop with the slippage past it visible, a live position carries reduce-only stop/take-profit orders on the exchange, and one button flattens a wallet.

---

## Execution Order Summary

| Sprint | Epic Focus |
|---|---|
| 0 | Align with upstream v0.3.1, run tests, scaffold routes |
| 1 | Epic 1 — Hyperliquid data adapter |
| 2 | Epic 2 — Strategy library & builder |
| 3 | Epic 3 — Backtesting lab |
| 4 | Epic 4 — Multi-wallet support |
| 5 | Epic 5 — Signal generation via TradingAgentsGraph |
| 6 | Epic 6 — Paper auto-trading |
| 7 | Epic 6/7 — Live execution + kill switch |
| 8 | Epic 7 — Portfolio & risk dashboard |
| 9 | Epic 8 — Alerts, reflection, UI polish |
| 10 | Stabilization & release |
| 11 | Epics 9–14 — Packaging, correctness, live PnL, security, frontend polish, testing |
| 12 | Epics 15–16 — Hyperliquid-accurate costs, charts, safe live config, walk-forward strategy search |
| 13 | Epic 17 — Security remediation (blocks mainnet) |
| 14 | Epic 18 — Live-trading readiness and reconciliation |
| 15 | Epics 19–20 — Research depth, chart consolidation, frontend tests |
| 16 | Epic 21 — Protective-exit enforcement, kill switch, order cancel |

---

## Risk & Contingency

| Risk | Mitigation |
|---|---|
| Hyperliquid API changes | Pin SDK version and keep adapter behind the `dataflows/interface.py` vendor abstraction. |
| LLM costs blow up | Default to cheaper models from `model_catalog` (`gpt-5.4-mini`, `claude-haiku-4-5`) and cache frequent analyses. |
| Live trading losses | Mandatory 7-day paper run before live; hard stop-loss and position caps. |
| Encrypted secret loss | Document key backup; never store plaintext; test recovery flow. |
| Scope creep | Stick to one epic per sprint; defer NFT/Polymarket exchange integration to V2. |
| Overfitting a "winner" | Rank on out-of-sample only, report the Deflated Sharpe Ratio for the number of trials, and refuse to promote a candidate whose DSR is not significant. |
| Mainnet default + open API | Deferred while the app is localhost-only with the port unpublished; treat Epic 17 as a prerequisite the moment it is exposed, and keep `LIVE_TRADING=false` and the per-wallet gate off until then. |
| Backtest assumes trade management the exchange will not do | Enforce protective exits in both execution paths (Epic 21); where the exchange cannot enforce a leg — Hyperliquid has no native trailing stop — say so on the position rather than assuming the backtest holds. |
| Live automation needs a signing key at rest | Live orders require the master password, so unattended live trading is out of scope until a deliberate session-unlock design lands (Epic 22). Paper automation carries no such risk. |

---

## How to Use This Plan

1. Pick the next sprint.
2. Move its user stories into your task tracker.
3. At the end of the sprint, run the app on `localhost` and verify the milestone.
4. Update this plan if priorities change (e.g. if live execution is needed sooner than paper).
