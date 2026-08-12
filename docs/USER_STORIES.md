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
