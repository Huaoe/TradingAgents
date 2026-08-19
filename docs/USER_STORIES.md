# User Stories — Hyperliquid Trading Agent App

Each user story follows:

> **As a** [persona], **I want** [feature], **so that** [benefit].

Acceptance criteria use:

- **Given** context
- **When** action
- **Then** expected result

---

## Epic 1: Hyperliquid Data Adapter

### US-1.1 View live market scanner
**As a** trader, **I want** to see a list of Hyperliquid perp and spot markets with price, 24h change, funding, and volume, **so that** I can identify what to analyze.

**Acceptance Criteria**
- Given I am on `/scanner`, when the page loads, then I see Symbol, Name, Type, Price, 24h, Volume, Funding, and Signal columns.
- Given the backend is connected to Hyperliquid Info API, when prices update, then the table refreshes within 5 seconds.

### US-1.2 Analyze a single market with Hyperliquid data
**As a** trader, **I want** to click "Analyze" on a market row, **so that** `TradingAgentsGraph` runs with Hyperliquid-native data.

**Acceptance Criteria**
- Given I click "Analyze" for SOL, when the analysis completes, then the backend calls `TradingAgentsGraph.run(asset_type="crypto", symbol="SOL", ...)`.
- Given the signal is produced, when it reaches the frontend, then it displays action, confidence, size, entry, stop, target, leverage, and reasoning.
- Given the analysis fails (no data or LLM error), when an error occurs, then I see a clear error message without crashing the page.

### US-1.3 Register Hyperliquid as a data vendor
**As a** a developer, **I want** `dataflows/interface.py` to route market-data calls to a Hyperliquid implementation, **so that** the agent graph can consume perp/spot data transparently.

**Acceptance Criteria**
- Given `default_config.py` sets `core_stock_apis: "hyperliquid"`, when `get_stock_data` is called, then `tradingagents.dataflows.hyperliquid.get_stock_data` is invoked.
- Given `get_stock_data` is called, when the symbol is `BTC`, then it requests Hyperliquid candles for `BTC` and returns a CSV string in the same format as the yfinance vendor.

---

## Epic 2: Strategy Library & Builder

### US-2.1 Browse predefined strategy templates
**As a** trader, **I want** to browse predefined strategy templates, **so that** I can start from a proven setup.

**Acceptance Criteria**
- Given I navigate to `/strategies`, when the page loads, then I see cards for Momentum Breakout, Mean Reversion, Funding Rate Arb, HYPE Delta Neutral, and Custom.
- Given I click a template, when the builder opens, then the form is pre-filled with sensible defaults.

### US-2.2 Create a custom strategy
**As a** trader, **I want** to select markets, agents, LLM provider/model, risk parameters, and execution mode, **so that** I can define my own strategy.

**Acceptance Criteria**
- Given I choose "Custom", when I fill the form, then I can select at least one market, one agent, one LLM provider/model from the upstream catalog, max allocation, max leverage, stop-loss, and execution mode.
- Given I click "Save", when validation passes, then the strategy appears in my saved list.
- Given I omit a required field, when I click "Save", then I see a validation error.

### US-2.3 Clone and edit a strategy
**As a** trader, **I want** to clone an existing strategy, **so that** I can iterate without breaking the original.

**Acceptance Criteria**
- Given I click "Clone" on a saved strategy, when the builder opens, then all settings are duplicated with "(Copy)" appended to the name.
- Given I edit the clone and save, when I return to the list, then the original and the clone both exist.

### US-2.4 Delete a strategy
**As a** trader, **I want** to delete a draft strategy, **so that** my list stays clean.

**Acceptance Criteria**
- Given I click "Delete" on a strategy, when I confirm, then the strategy is removed and active/paused strategies cannot be deleted without stopping them first.

---

## Epic 3: Backtesting Lab with Statistics

### US-3.1 Run a backtest
**As a** trader, **I want** to select a strategy, date range, and initial balance, then run a backtest, **so that** I can validate the strategy historically.

**Acceptance Criteria**
- Given I am on `/backtest`, when I choose a strategy and date range and click "Run", then the backtest executes and results load.
- Given the backtest is running, when it is in progress, then I see a loading indicator.

### US-3.2 View headline statistics at the top
**As a** trader, **I want** the most important backtest statistics displayed prominently at the top of the page, **so that** I can assess performance at a glance.

**Acceptance Criteria**
- Given the backtest results load, when I view the page, then I see cards for Total Return, Sharpe, Max Drawdown, Win Rate, Profit Factor, # Trades, Avg Trade, and Benchmark Return at the top, above the fold.
- Given the statistic is negative, when displayed, then it is colored red; positive values are green.

### US-3.3 Inspect equity curve and trades
**As a** trader, **I want** to see the equity curve, drawdown, and a trade list, **so that** I understand when and why the strategy won or lost.

**Acceptance Criteria**
- Given the backtest completes, when I scroll below the statistics, then I see an equity curve chart, drawdown chart, and a sortable trades table.
- Given I click a trade row, when the details open, then I see entry, exit, size, PnL, duration, and reasoning.

### US-3.4 Activate a strategy from a backtest
**As a** trader, **I want** to promote a successful backtest to a paper or live strategy, **so that** I do not have to re-enter parameters.

**Acceptance Criteria**
- Given I am viewing a backtest with positive Sharpe and acceptable drawdown, when I click "Activate as Paper Strategy", then a new strategy is created in paper mode with the same parameters.

---

## Epic 4: Multi-Wallet Support

### US-4.1 Add a new wallet
**As a** trader, **I want** to add a Hyperliquid API wallet with a label, **so that** I can trade from multiple accounts.

**Acceptance Criteria**
- Given I navigate to `/wallets`, when I click "Add Wallet", then I can enter a label, wallet address, and encrypted API secret.
- Given I submit the form, when the wallet is saved, then it appears in the wallet list.

### US-4.2 Switch active wallet
**As a** trader, **I want** to switch the active wallet from any page, **so that** I can quickly trade from a different account.

**Acceptance Criteria**
- Given a wallet switcher in the sidebar/header, when I select a wallet, then the dashboard, positions, and orders update to that wallet.
- Given a strategy is assigned to a wallet, when I switch wallet, then strategy cards still show their assigned wallet.

### US-4.3 View combined and per-wallet PnL
**As a** trader, **I want** to see both combined and per-wallet PnL, **so that** I can compare account performance.

**Acceptance Criteria**
- Given I am on the dashboard, when I view the PnL section, then I see a combined total and individual wallet breakdowns.

---

## Epic 5: Signal Generation via TradingAgentsGraph

### US-5.1 Run the upstream graph for crypto
**As a** trader, **I want** `TradingAgentsGraph` to run in crypto mode for a Hyperliquid market, **so that** signals are based on relevant perp/spot data.

**Acceptance Criteria**
- Given I request a signal for `BTC` with `asset_type="crypto"`, when the graph runs, then it uses the Hyperliquid vendor and excludes the fundamentals analyst.
- Given the graph completes, when the result is returned, then it contains a `PortfolioDecision` and a `TraderProposal`.

### US-5.2 Display structured signal output
**As a** trader, **I want** to see the typed `PortfolioDecision`, `TraderProposal`, and `SentimentReport` in the UI, **so that** I can understand the agents' decision and sentiment.

**Acceptance Criteria**
- Given I open a signal card, when it renders, then I see the rating (`Buy / Overweight / Hold / Underweight / Sell`), confidence, size, leverage, entry, stop, target, and reasoning.
- Given a `SentimentReport` exists, when the card renders, then it shows the sentiment band, score, and confidence.

### US-5.3 Normalize signal for execution
**As a** the execution engine, **I want** the signal converted to a strict order schema, **so that** I can place orders without parsing free text.

**Acceptance Criteria**
- Given a `PortfolioDecision` and `TraderProposal`, when the signal service processes them, then it returns an object with `action`, `symbol`, `size`, `entry`, `stop`, `target`, `leverage`, `walletId`, `strategyId`.
- Given a required field is missing, when validation runs, then the signal is rejected and logged.

---

## Epic 6: Auto-Trading & Execution Engine

### US-6.1 Set execution mode per strategy
**As a** trader, **I want** to choose manual, auto-confirm, or fully automatic execution for each strategy, **so that** I control how hands-off the bot is.

**Acceptance Criteria**
- Given I edit a strategy, when I open the execution section, then I can select one of the three modes.
- Given the mode is "manual", when a signal is generated, then it appears in the Signal Feed and waits for my action.
- Given the mode is "fully automatic", when a signal passes risk filters, then it is executed immediately.

### US-6.2 Paper-trade an order
**As a** trader, **I want** to run strategies in paper mode, **so that** I can prove alpha without risking capital.

**Acceptance Criteria**
- Given a strategy is in paper mode, when a signal executes, then the order is simulated using live price data and recorded in the paper portfolio.
- Given a paper trade fills, when PnL is computed, then fees and slippage are applied.

### US-6.3 Submit a live order to Hyperliquid
**As a** trader, **I want** accepted or auto-approved signals to be submitted as signed orders to Hyperliquid, **so that** the bot trades for real.

**Acceptance Criteria**
- Given I click "Execute Live" or auto-trading is enabled, when the order is built, then it is signed with the strategy's wallet and submitted via the Hyperliquid Exchange API.
- Given the order is submitted, when Hyperliquid responds, then the status is updated to filled/open/failed and the user is notified.

### US-6.4 Enforce slippage and trade limits
**As a** trader, **I want** the engine to reject orders that exceed slippage or daily trade limits, **so that** I am protected from runaway execution.

**Acceptance Criteria**
- Given a signal fill price is >1% from the signal price, when the slippage guard runs, then the order is cancelled and an alert is sent.
- Given a strategy has already traded 10 times today, when an 11th signal fires, then it is queued or rejected based on user setting.

---

## Epic 7: Portfolio, Positions & Risk Management

### US-7.1 View open positions
**As a** trader, **I want** to see all my open perp and spot positions, **so that** I can monitor exposure.

**Acceptance Criteria**
- Given I am on `/positions`, when the page loads, then I see a table with Symbol, Side, Size, Entry, Mark, PnL, Leverage, and Liquidation Price.
- Given I have positions in multiple wallets, when I view the table, then each row shows its wallet.

### US-7.2 View open orders and cancel
**As a** trader, **I want** to see open orders and cancel them, **so that** I can manage working orders.

**Acceptance Criteria**
- Given I am on `/orders`, when the page loads, then I see open and filled orders.
- Given I click "Cancel" on an open order, when confirmed, then the order is cancelled via the Hyperliquid API.

### US-7.3 Kill switch
**As a** trader, **I want** a kill switch that cancels all orders and flattens positions, **so that** I can stop losses instantly in an emergency.

**Acceptance Criteria**
- Given I click the kill switch, when it activates, then all open orders for the selected wallet are cancelled and open perp positions are market-closed.
- Given the kill switch runs, when complete, then I see a confirmation with the actions taken.

---

## Epic 8: Alerts, Reflection & UI Polish

### US-8.1 Receive trade alerts
**As a** trader, **I want** to receive alerts for new signals, fills, and stop-loss hits, **so that** I stay informed without watching the app.

**Acceptance Criteria**
- Given a new signal is generated, when it matches my alert settings, then I receive an in-app notification and optionally a Telegram/Discord message.
- Given a stop-loss is hit, when the fill occurs, then an alert is sent within 10 seconds.

### US-8.2 Reflect on closed trades
**As a** the system, **I want** to feed realized PnL back into the agents' memory, **so that** future signals improve.

**Acceptance Criteria**
- Given a trade closes, when the reflection job runs, then `reflect_and_remember()` is called with the trade return.
- Given I visit `/memory`, when the page loads, then I see a list of lessons learned from recent trades.

### US-8.3 Mobile-responsive UI
**As a** trader, **I want** the app to work on my phone, **so that** I can check positions on the go.

**Acceptance Criteria**
- Given I open the app on a 375px-wide device, when I navigate the main pages, then all tables and cards are usable without horizontal scrolling.
- Given the sidebar is open on mobile, when I tap outside, then it closes.

### US-8.4 Risk disclaimer
**As a** trader, **I want** clear disclaimers before live trading, **so that** I understand the risks.

**Acceptance Criteria**
- Given I attempt to activate a live strategy for the first time, when the modal opens, then I must acknowledge "This is not financial advice and I may lose capital" before proceeding.

---

## Epic 9: Packaging, Deployment & Developer Experience *(Done)*

### US-9.1 Add app-level Python packaging
**As a** developer, **I want** `app/` to have its own `pyproject.toml` or `requirements.txt`, **so that** the FastAPI backend dependencies are explicit and installable.

**Acceptance Criteria**
- Given I clone the repo, when I run `pip install -e app/`, then `fastapi`, `uvicorn`, `pydantic`, `hyperliquid-python-api`, `cryptography`, `numpy`, `pandas`, and `tradingagents` are installed.
- Given `app/pyproject.toml` exists, when I read it, then it pins compatible versions of all non-engine dependencies.

### US-9.2 Fix Docker build
**As a** operator, **I want** `docker compose -f app/docker-compose.web.yml up --build` to work, **so that** I can deploy the app without manual setup.

**Acceptance Criteria**
- Given a clean environment, when I run the compose command, then the image builds and the backend starts on port 8000.
- Given the container is running, when I open `http://localhost:8000`, then I see the React app served from `frontend/dist`.

### US-9.3 Update runbook
**As a** developer, **I want** `docs/RUNBOOK.md` to match the current directory layout, **so that** new contributors can run the app correctly.

**Acceptance Criteria**
- Given I follow the runbook, when I run the backend, then the command is `cd app && python -m backend.main`.
- Given I follow the runbook, when I run the frontend, then the command is `cd app/frontend && npm run dev`.
- Given I follow the runbook, when I run lint, then the command is `ruff check app/backend`.

### US-9.4 Add CI for the app
**As a** maintainer, **I want** GitHub Actions to test the app, **so that** regressions are caught before merging.

**Acceptance Criteria**
- Given a pull request, when CI runs, then `ruff check app/backend`, `pytest app/backend/tests`, and `npm run build` in `app/frontend` all pass.

---

## Epic 10: Backtest Correctness & Live/Backtest Consistency *(Done; US-10.3 Sharpe still uses equity-curve pct-change and can be refined to returns-on-capital)*

### US-10.1 Remove look-ahead bias
**As a** quant, **I want** backtest indicators to be calculated only from past bars, **so that** results are realistic.

**Acceptance Criteria**
- Given a strategy uses `sma20`, when a signal is computed for bar `i`, then `sma20` does not include the close of bar `i`.
- Given the backtest runs, when it enters a position, then the entry price is the next bar's open or the current bar's close (documented and consistent).

### US-10.2 Unify live and backtest template logic
**As a** trader, **I want** the same template rules used in backtest and live signal generation, **so that** a backtested strategy behaves the same in production.

**Acceptance Criteria**
- Given a `turtle_breakout` strategy, when I run a backtest and then generate live signals over the same period, then the long/short/flat signals match within tolerance.
- Given a template does not have live logic yet, when the user tries to run it live, then the UI shows "Live not supported for this template yet".

### US-10.3 Fix Sharpe calculation
**As a** trader, **I want** the Sharpe ratio to be computed from stable returns, **so that** it is comparable across strategies.

**Acceptance Criteria**
- Given a backtest completes, when I view the Sharpe ratio, then it is based on percent returns on deployed capital or log returns, not equity-curve first differences.
- Given a volatile but flat strategy, when the Sharpe is computed, then it stays within a realistic range (e.g., -5 to +5) rather than -18.

### US-10.4 Add template regression tests
**As a** developer, **I want** each strategy template tested on synthetic OHLCV data, **so that** template changes do not silently break signals.

**Acceptance Criteria**
- Given a synthetic 200-bar dataset, when each template runs, then it produces a mix of long, short, and flat signals without exceptions.
- Given a template is modified, when tests run, then the signal distribution is compared to a recorded baseline and flagged if it changes significantly.

---

## Epic 11: Real-Time Portfolio & PnL *(Done)*

### US-11.1 Refresh mark price for open positions
**As a** trader, **I want** open positions to update with the current Hyperliquid mark price, **so that** I see live unrealized PnL.

**Acceptance Criteria**
- Given an open LONG position, when the mark price changes, then the position's `markPrice` and `pnl` are updated within 10 seconds.
- Given a SHORT position, when the mark price rises, then `pnl` becomes more negative.

### US-11.2 Show live unrealized PnL
**As a** trader, **I want** the Dashboard and Positions page to show live PnL, **so that** I can monitor my portfolio.

**Acceptance Criteria**
- Given I am on `/positions`, when the page loads, then each row shows `markPrice` and live `pnl`.
- Given I am on `/`, when the dashboard loads, then the `Unrealized PnL` card reflects live mark prices.

### US-11.3 Replace mock equity chart with real data
**As a** trader, **I want** the Dashboard equity curve to be real, **so that** I trust the portfolio overview.

**Acceptance Criteria**
- Given I have executed trades, when I open the Dashboard, then the equity curve is built from stored portfolio snapshots, not `equityData` from `mockData.ts`.
- Given the backend has no trades, when the dashboard loads, then the chart shows a flat line at the starting balance instead of mock sample data.

### US-11.4 Store portfolio equity history
**As a** the system, **I want** to record periodic portfolio value snapshots, **so that** the equity curve is accurate over time.

**Acceptance Criteria**
- Given the backend is running, when a background job runs every minute, then it records `wallet_id`, `timestamp`, and `total_value`.
- Given I open the Dashboard, when it fetches history, then it shows at most one point per minute.

---

## Epic 12: Security & Risk Hardening *(Done)*

### US-12.1 Use unique per-wallet encryption salt
**As a** trader, **I want** each wallet secret encrypted with a unique salt, **so that** a compromised password does not decrypt all wallets.

**Acceptance Criteria**
- Given I create two wallets with the same master password, when their encrypted keys are compared, then they are not identical.
- Given a wallet is created, when the salt is stored, then it is different for every wallet.

### US-12.2 Add live trading confirmation
**As a** trader, **I want** an explicit confirmation before any live order, **so that** I do not accidentally trade real capital.

**Acceptance Criteria**
- Given I attempt to execute a live signal, when the order is about to be sent, then a modal shows symbol, side, size, leverage, and wallet.
- Given the modal is open, when I click "Confirm", then the order is submitted; when I click "Cancel", then it is not.

### US-12.3 Validate provider/model in strategy editor
**As a** system, **I want** `llmProvider` and `llmModel` validated against the upstream catalog, **so that** strategies do not reference unavailable models.

**Acceptance Criteria**
- Given a user selects `glm` / `glm-5-turbo` (which is in `model_catalog`), when they save, then the strategy is accepted.
- Given a user selects `openai` / `invalid-model`, when they save, then the frontend shows a validation error.

### US-12.4 Sanitize API error responses
**As a** trader, **I want** the backend to return generic error messages, **so that** internal details are not exposed.

**Acceptance Criteria**
- Given an unexpected exception occurs, when the frontend receives the response, then the detail is a short, user-friendly message, not a full stack trace.
- Given an exception occurs, when the backend logs it, then the full stack trace is written to the server logs.

---

## Epic 13: Frontend Polish & Real Data *(Done)*

### US-13.1 Remove mock data fallbacks
**As a** trader, **I want** the app to show real data or clear empty states, **so that** I am not misled by sample charts.

**Acceptance Criteria**
- Given the backend is unavailable, when `fetchAccount` fails, then the Dashboard shows an error message instead of `mockAccount`.
- Given there are no trades, when the Dashboard loads, then the equity chart is a flat line, not `equityData`.

### US-13.2 Add loading and error states
**As a** trader, **I want** clear loading and error feedback, **so that** I know when data is missing.

**Acceptance Criteria**
- Given a page is fetching data, when it takes >500ms, then a loading skeleton or spinner is shown.
- Given a fetch fails, when the page renders, then an error banner with a retry button is shown.

### US-13.3 Fix fast-refresh warning
**As a** developer, **I want** `WalletContext` to satisfy fast-refresh rules, **so that** the lint warning is gone.

**Acceptance Criteria**
- Given I run `npm run lint`, when the output is generated, then there are no `only-export-components` warnings.
- Given `WalletContext` is refactored, when the app runs, then provider and hook still work correctly.

### US-13.4 Improve strategy editor validation/labels
**As a** trader, **I want** the strategy editor to clearly label percentage and absolute fields, **so that** I do not misconfigure thresholds.

**Acceptance Criteria**
- Given I am editing `riskConfig`, when I see the funding threshold fields, then the label indicates the value is a percentage (e.g., "Long Funding Threshold (%)").
- Given I enter `5` in the allocation field, when saved, then the backend receives `0.05`, not `5`.

---

## Epic 14: Testing & Observability *(Partial; US-14.3 frontend component tests not added and `/api/health` does not yet probe DB/Hyperliquid)*

### US-14.1 Add backend endpoint smoke tests
**As a** developer, **I want** all FastAPI endpoints covered by smoke tests, **so that** broken routes are caught in CI.

**Acceptance Criteria**
- Given `TestClient` is set up, when it calls `/api/health`, `/api/markets`, `/api/backtest`, `/api/signals`, and `/api/strategies`, then each returns a 2xx or documented 4xx status.
- Given a test run completes, when I view coverage, then all main routes have at least one test.

### US-14.2 Add backtest unit tests
**As a** developer, **I want** the backtest engine tested with synthetic data, **so that** logic changes do not break existing templates.

**Acceptance Criteria**
- Given a 200-bar synthetic OHLCV dataset, when `run_backtest` is called for each template, then it completes without exception.
- Given a known deterministic dataset, when the backtest runs, then the total return and trade count match a recorded snapshot.

### US-14.3 Add frontend component tests
**As a** developer, **I want** key React components tested, **so that** UI regressions are caught.

**Acceptance Criteria**
- Given `Backtest` renders with sample `BacktestResult` props, when the page loads, then statistics and charts are displayed.
- Given `StrategyEditor` opens with a template query parameter, when it loads, then the form is pre-filled with the template defaults.

### US-14.4 Add structured logging and health checks
**As a** operator, **I want** the app to log structured events and expose health checks, **so that** I can monitor it in production.

**Acceptance Criteria**
- Given a backtest runs, when it completes, then a structured log line is emitted with `duration_ms`, `symbol`, `interval`, and `total_return_pct`.
- Given I call `/api/health`, when the backend is healthy, then it returns `status: ok` plus `db: ok` and `hyperliquid: ok`.

---

## Epic 16: Strategy Search & Selection Discipline *(Done)*

### US-16.1 Search parameter space with walk-forward validation
**As a** trader, **I want** every template and parameter variant scored on data it was not selected on, **so that** the ranking is not just a record of what fitted best.

**Acceptance Criteria**
- Given a symbol, interval and date range, when I run a search, then each fold trains on all earlier blocks and is scored on the next unseen block only.
- Given a candidate that never traded in a fold, when results are aggregated, then that fold is scored zero rather than dropped from its median.

### US-16.2 Know whether the winner is luck
**As a** trader, **I want** the winner's Sharpe discounted by the number of variants tried, **so that** I do not trade the luckiest of 128 coin flips.

**Acceptance Criteria**
- Given a completed search, when I read the verdicts, then a Deflated Sharpe Ratio is shown with an explicit significant/not-significant statement and the trial count.
- Given too few trials or observations to compute it, when I read the verdicts, then a reason is shown instead of a fabricated number.

### US-16.3 See performance by market regime
**As a** trader, **I want** results broken down by funding and volatility regime, **so that** I can ask when a strategy worked rather than whether it worked.

**Acceptance Criteria**
- Given a candidate's trades, when the breakdown is computed, then each trade is attributed to the regime observable at or before entry, using shifted trailing statistics.
- Given a bucket with fewer than five trades, when it is displayed, then it is marked as a thin sample rather than hidden.

---

## Epic 17: Security Remediation *(Next)*

### US-17.1 Stop the SPA route serving arbitrary files
**As an** operator, **I want** the frontend catch-all to serve only files inside the build directory, **so that** the wallet database cannot be downloaded over HTTP.

**Acceptance Criteria**
- Given a request whose path resolves outside `FRONTEND_DIST` (including percent-encoded traversal), when it hits the catch-all, then the response is 404 and no file content is returned.
- Given the traversal path used in the review (`/..%2f..%2fbackend%2fdata%2fwallets.db`), when a test requests it, then the test asserts a 404.

### US-17.2 Never return wallet key material
**As a** wallet owner, **I want** key material to stay server-side, **so that** reading an API response cannot start an offline attack on my private key.

**Acceptance Criteria**
- Given any wallet endpoint, when it returns a wallet, then the body contains neither `encryptedKey` nor `salt`.
- Given the frontend, when it lists wallets, then it still works without those fields.

### US-17.3 Remove runtime databases from version control
**As a** maintainer, **I want** no `.db` file tracked in git, **so that** a clone does not hand over stored wallets and history.

**Acceptance Criteria**
- Given a fresh clone, when I run `git ls-files`, then no `.db` path is listed and `.gitignore` covers `app/backend/data/*.db`.
- Given the previously committed `wallets.db`, when remediation is complete, then any key it held has been rotated and this is recorded in the runbook.

### US-17.4 Require authentication for mutating endpoints
**As an** operator, **I want** state-changing endpoints to require a token, **so that** anything that can reach the port cannot place orders or add wallets.

**Acceptance Criteria**
- Given no or a wrong token, when a request hits a mutating endpoint, then it is rejected with 401 and no state changes.
- Given no explicit opt-in, when the backend or container starts, then it binds to loopback rather than `0.0.0.0`.
