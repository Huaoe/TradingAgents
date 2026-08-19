# HL Agents — User Wiki

A complete, jargon-free guide to the Hyperliquid Trading Agent app in this repository.

**Read this first:** this app can place real orders with real money. It starts in **paper mode**
(simulated trading, no real orders). Nothing you do can send a real order until you deliberately
switch on three separate safety gates (see [Going live](#12-going-live-the-three-gates)).

Every finance term used in the UI is defined in plain English in the [Glossary](#14-glossary).
If a word looks unfamiliar, jump there — the glossary is the point of this document.

---

## Table of contents

1. [What this app actually does](#1-what-this-app-actually-does)
2. [Core concepts in plain English](#2-core-concepts-in-plain-english)
3. [Install and run it](#3-install-and-run-it)
4. [Your first 10 minutes (guided walkthrough)](#4-your-first-10-minutes-guided-walkthrough)
5. [Wallets](#5-wallets)
6. [Dashboard](#6-dashboard)
7. [Scanner](#7-scanner)
8. [Signals](#8-signals)
9. [Positions & Orders](#9-positions--orders)
10. [Strategies (and the strategy editor)](#10-strategies-and-the-strategy-editor)
11. [Backtest Lab and Strategy Finder](#11-backtest-lab-and-strategy-finder)
12. [Going live: the three gates](#12-going-live-the-three-gates)
13. [Alerts and Journal](#13-alerts-and-journal)
14. [Glossary](#14-glossary)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. What this app actually does

The app trades **crypto perpetual futures** on **Hyperliquid** (see glossary for both terms).
The workflow is always the same four steps:

1. **Analyse a market** — the app downloads recent price history from Hyperliquid and runs a
   strategy over it. Optionally, AI language models (LLMs) write the reasoning.
2. **Produce a signal** — a suggestion: buy, sell, or do nothing, with a size, a stop, a target
   and a confidence score.
3. **You approve or reject it** — nothing is executed until you press Accept.
4. **The position is tracked** — profit/loss, protective exits, and a journal entry once closed.

Two extra tools let you check an idea against the past before risking anything:
**Backtest Lab** (test one strategy) and **Strategy Finder** (test many parameter combinations
honestly, i.e. without fooling yourself — see [section 11](#11-backtest-lab-and-strategy-finder)).

**What the app does not do:** it does not trade on its own. There is no scheduler running in the
background. The `Execution mode` and `Schedule` fields on a strategy are saved as notes for the
future, but no code reads them yet — every trade starts with you clicking **Analyze**/**Generate**
and then **Accept**.

---

## 2. Core concepts in plain English

**Spot vs. perpetual.** Buying *spot* means you own the coin. A *perpetual* ("perp") is a contract
that merely tracks the coin's price — you never own the coin, you just profit or lose as the price
moves. Perps let you bet on prices going *down* and let you use *leverage*.

**Long vs. short.** *Long* = you profit if the price goes up. *Short* = you profit if the price
goes down.

**Leverage.** Borrowed size. With $100 and 5x leverage you control a $500 position, so every 1%
price move becomes 5% of your money. It multiplies gains **and** losses, and it is why
*liquidation* exists.

**Margin and liquidation.** *Margin* is the money set aside as collateral for a position.
If the price moves against you far enough that the margin is nearly gone, the exchange closes the
position for you — that is a *liquidation*, and it usually means losing all the margin on it.
The `Liq. Price` column is the price at which that happens.

**Funding rate.** Perps have no expiry, so the exchange keeps their price glued to the real coin
price by having one side pay the other a small fee, usually every hour. Positive funding = longs
pay shorts (the crowd is bullish). Negative funding = shorts pay longs. It is a cost or an income
stream while you hold a position, and several strategies in this app exist purely to collect it.

**Fees, maker vs. taker, slippage.** A *taker* order fills instantly against existing orders and
pays a higher fee; a *maker* order waits in the order book and pays a lower fee (or gets a rebate).
*Slippage* is the extra cost of the price moving as your order fills. All three eat returns and are
modelled explicitly in the backtester — that is deliberate, because ignoring them is the classic
way to produce a beautiful but fake backtest.

**PnL.** "Profit and loss". *Unrealized* PnL is the paper gain/loss on positions still open;
*realized* PnL is locked in after closing. *Gross* PnL is before fees and funding, *net* PnL after.

---

## 3. Install and run it

Prerequisites: Python 3.10+, Node.js 20+, Git.

```bash
git clone https://github.com/Huaoe/TradingAgents.git
cd TradingAgents

pip install -e engine/          # the analysis engine
pip install -e "app/[dev]"      # the backend

cd app/frontend && npm install
```

Configure the environment (from the repository root):

```bash
cp .env.example .env
```

The only settings that matter on day one:

| Variable | What it does |
| --- | --- |
| `LIVE_TRADING` | Master switch for real orders. Leave `false`. |
| `HYPERLIQUID_NETWORK` | `mainnet` (real market data, default) or `testnet` (fake money network). Applies to both data and orders. |
| `OPENAI_API_KEY` (or another provider key) | Optional. Without any key the app uses its built-in rule engine instead of AI models — perfectly fine for learning. |
| `LLM_COST_INPUT_PER_1M` / `LLM_COST_OUTPUT_PER_1M` | The prices used to estimate what your AI usage costs, shown on the Dashboard. |

Run it in two terminals:

```bash
# terminal 1 — backend API on http://localhost:8000
cd app && python -m backend.main

# terminal 2 — web UI on http://localhost:5173
cd app/frontend && npm run dev
```

Open <http://localhost:5173>. Docker alternative:
`docker compose -f app/docker-compose.web.yml up --build -d`, then <http://localhost:8000>.

---

## 4. Your first 10 minutes (guided walkthrough)

1. **Add a wallet** — go to **Wallets → Add Wallet**. For learning, invent a name, paste any
   `0x…`-looking address and any dummy private key, and set a master password of 8+ characters.
   In paper mode the key is never used to sign anything; it is stored encrypted with your master
   password. Tick *Set as default*.
2. **Select it** in the sidebar dropdown under **Active Wallet**. Most pages show data for the
   selected wallet only.
3. **Scan a market** — go to **Scanner**, leave *Strategy* as `Default`, leave *Use LLM* unticked
   (free and instant), find `BTC` and click **Analyze**. A signal appears in a violet card.
4. **Read the signal** — action (BUY/SELL/HOLD), confidence, size, stop, target, and the reasoning
   text. See [section 8](#8-signals) for what each field means.
5. **Accept it** — go to **Signals**, make sure *Execution mode* on the card says **Paper**, and
   click **Accept**. A simulated position is opened.
6. **Watch it** — **Positions** shows the open position, its mark price, PnL, leverage and
   liquidation price, plus a **Close** button. **Dashboard** shows the account totals.
7. **Close it** — press **Close**. The trade moves to **Closed Positions** and a record appears in
   the **Journal**.

You have now completed the whole loop without risking anything.

---

## 5. Wallets

*Sidebar → Wallets.* A "wallet" here is a Hyperliquid account the app can trade for.

| Field | Meaning |
| --- | --- |
| Name | Your label, e.g. "paper test". |
| Address | The public `0x…` account address. Safe to share. |
| Private Key | The secret that authorises orders. **Never share it.** Stored encrypted, never in plain text; only used for live orders and other live actions. |
| Master Password | The password (8+ chars) that encrypts the private key. You must retype it for every live order, close, cancellation or kill switch action. If you lose it, the key cannot be recovered — re-add the wallet. |
| Default wallet | The wallet pre-selected when the app starts (star badge). |

The sidebar **Active Wallet** selector decides which wallet's positions, orders, alerts and journal
you are looking at. The sidebar also shows a permanent **Paper Mode / No real orders sent** note as
a reminder of the app's default.

For real trading the account needs USDC on Hyperliquid mainnet (bridged via Arbitrum). Execution
also works with an approved Hyperliquid **API agent wallet** — a key that may trade the account but
cannot withdraw funds, which is the safer way to run any bot.

---

## 6. Dashboard

*Sidebar → Dashboard.* The account overview for the selected wallet.

Badges at the top right:

- **PAPER / LIVE** — whether the wallet is in simulation or real trading.
- **Balance: paper store / exchange** — whether the numbers come from the app's local simulation
  database or from real balances read off Hyperliquid.
- **MAINNET / TESTNET** — which Hyperliquid network is configured.

Top row of numbers:

| Stat | Meaning |
| --- | --- |
| Total Value | Everything the account is worth: cash plus the current value of open positions. Also called *equity*. |
| … available | Cash not tied up as margin, i.e. what you could still deploy. |
| Unrealized PnL | Profit/loss of open positions if you closed them right now. |
| Daily PnL | Profit/loss accumulated today. |
| Margin Used | Money currently locked as collateral, and what share of the account that is. High = little room for adverse moves. |

Second row is AI cost tracking: **LLM Spend** (estimated dollars, using the rates in `.env`),
**LLM Tokens** (units of text sent to/received from the model — how usage is billed) and
**LLM Calls** (number of model requests). These matter because analysis with *Use LLM* ticked costs
real money per click.

**Equity Curve (Paper)** — your total value over time, sampled once a minute while the backend
runs. A rising curve is the goal; how *smoothly* it rises matters as much as where it ends.

**Risk Snapshot** — how exposed you are right now:

- *Open positions* — how many trades are live.
- *Total notional* — combined face value of those positions (size × price), i.e. the amount of
  market you actually control, which with leverage is much larger than your balance.
- *Max exposure* — the single biggest position, by notional. Concentration risk.
- *Max leverage* — the highest leverage in use across positions.

Then **Recent Signals** and **Open Positions** as quick lists.

---

## 7. Scanner

*Sidebar → Scanner.* The market list, and where you launch an analysis.

Controls: a market filter box, a **Strategy** dropdown (`Default` uses generic built-in rules) and a
**Use LLM** checkbox — untick it for a free deterministic answer, tick it to have AI agents write
the reasoning (costs money, needs a provider key in `.env`).

Table columns:

| Column | Meaning |
| --- | --- |
| Market | Ticker (`BTC`, `ETH`, …) and name. |
| Type | `perp` (contract, leverage possible) or `spot` (owning the coin). |
| Price | Latest traded price. |
| 24h | Percentage change over the last 24 hours. |
| Volume | Value traded in 24h, in millions. Higher volume = easier to get in and out. |
| Funding | The current hourly funding rate as a percentage. Positive = longs pay shorts. |
| OI | *Open interest*: the value of all outstanding contracts on that market. Rising OI with rising price means new money is backing the move. |
| Signal | The latest signal produced for that market, with its confidence. |
| Action | **Analyze** — run the strategy on that market now. |

The result also appears as **Latest Signal** at the top, including the AI token/cost breakdown when
LLM mode was used.

---

## 8. Signals

*Sidebar → Signals.* The list of suggestions, and the only place trades get approved.

**Generate Signal** creates one directly: type a **Symbol**, pick a **Strategy**, optionally tick
**Use LLM**, press **Generate**.

Each signal card contains:

| Field | Meaning |
| --- | --- |
| BUY / SELL / HOLD | Suggested action. BUY opens a long, SELL opens a short, HOLD means stay out. |
| Reasoning | Why the strategy concluded that — written by the rule engine or the AI agents. |
| Confidence | A 0–100 score for how strong the setup is. A strategy's *confidence floor* is the minimum score needed to act. |
| Size | The dollar value of the intended position (its notional). |
| Leverage | How much borrowed size the trade would use. |
| Entry | The price the trade is expected to open at. |
| Stop | The *stop loss*: the price at which the trade is abandoned to cap the loss. |
| Target | The *take profit*: the price at which gains are banked. |
| Agent tags | Which analysts contributed: **Market** (price/trend), **Funding** (funding rates), **OrderBook** (resting buy/sell orders), **Sentiment** (crowd mood), **News** (headlines). |

Then choose an **Execution mode** and act:

- **Paper** + **Accept** → simulated fill, position opens instantly, no real money.
- **Live** + **Accept** → a confirmation dialog asks for your master password, then a **real market
  order** is sent (only if all three live gates are on, see [section 12](#12-going-live-the-three-gates)).
- **Reject** → mark the signal as declined. The trash icon deletes it.

---

## 9. Positions & Orders

*Sidebar → Positions.* Everything currently at risk, plus history.

**Exchange Reconciliation.** A background check that compares what the app believes it holds
against what Hyperliquid actually reports, so a silent mismatch cannot go unnoticed. Statuses:
`ok` (they match), `diverged` (they do not — read the listed divergences carefully),
`unavailable` (the exchange could not be reached), `not_applicable` (nothing live to compare).
**Reconcile now** runs it on demand; it also runs automatically about once a minute for live wallets.

**Kill switch.** The emergency stop. Choose `live` or `paper` and press **Activate kill switch**:
it disables the wallet's live-trading permission first, then cancels resting orders and closes
(*flattens*) open positions, then reports what happened per order/position. Use it when something
is behaving in a way you do not understand.

**Open Positions** columns:

| Column | Meaning |
| --- | --- |
| Market / Mode | Ticker; `paper` or `live`. |
| Side | LONG or SHORT. |
| Size | Quantity in coins. |
| Entry | Price you got in at. |
| Mark | Current reference price used for PnL and liquidation. |
| PnL | Money and percentage gain/loss, plus its source: `exchange` (read from Hyperliquid) or `mark_price` (computed locally). |
| Leverage | Multiplier in use. |
| Liq. Price | Price that would trigger liquidation. |

Under the ticker, the protective-exit detail shows the position's active **stop**, **take profit**
and **trailing stop** (a stop that follows the price up, locking in gains — the *watermark* is the
best price reached so far). The app monitors these about every 10 seconds for paper positions, and
for live positions it places matching reduce-only trigger orders on the exchange and warns if they go
missing while the exchange position remains open. Live trailing stops are unsupported by Hyperliquid.
`Close` exits the position immediately at market.

**Closed Positions** shows the exit price and the **Trigger / Fill** pair — the price that was
supposed to trigger the exit versus the price actually obtained (the difference is slippage) — plus
the *exit reason*: `signal`, `stop_loss`, `take_profit`, `trailing_stop` or `end_of_backtest`.

**Resting Exchange Orders** lists live orders sitting on Hyperliquid that have not filled yet
(including your protective triggers), each cancellable. **Orders** below is the local fill history:
side, size, price, `Market`/`Limit` type, status and time.

---

## 10. Strategies (and the strategy editor)

*Sidebar → Strategies.* Pick a **Template** to start from, or edit a **Saved Strategy**.

### The templates

| Template | Idea, in plain terms |
| --- | --- |
| Momentum Breakout | Buy when price confirms an upward trend and sell when it confirms a downward trend — bet the move continues. |
| Mean Reversion | Buy panic, sell euphoria: act when indicators say price is stretched too far and should snap back. |
| Funding Rate Arb | When funding gets extreme, take the paid side and collect the fee. |
| HYPE Delta Neutral | Trade extreme funding in one direction; despite the name, this template does not open an offsetting spot/perpetual pair. |
| Trend Following | Ride established up/down trends confirmed by moving averages. |
| Scalp Momentum | Trade short-term Bollinger-band breakouts in the trend direction. |
| News Event | React to unusually wide, directional candle moves. |
| Basis Arbitrage | Fade extreme funding as a proxy for spot/perpetual basis convergence. |
| Grid Trading | In a sideways market, signal long near the bottom of the recent range and short near the top. |
| Dual Thrust | Classic breakout system using bands built from the recent high/low/close range. |
| Turtle Breakout | The famous Turtle rules: buy new N-period highs, sell new N-period lows. |
| EMA Bands Trend Catch | Trend entries on moving-average band breaks, exits when indicators look exhausted. |
| ATR-RSI Combo | Only trade when volatility expands *and* momentum is at an extreme. |
| Time Series Momentum | Go with the sign of the last N bars' return — a well-documented academic effect. |
| Overnight Seasonality (BTC) | Long-only, held during the 22:00–23:59 UTC window, flat otherwise. |
| Custom | Configure your own markets, agents, model and risk; the signal engine uses generic fallback rules. |

### The editor

**General** — name, template, description.

**Agents & Model** — which analysts to use, and the AI: **Provider** (OpenAI, Anthropic, …),
**Mode** (`quick` = fast/cheap model, `deep` = slower/stronger model for harder reasoning) and
**Model**.

**Markets** — the tickers the strategy applies to. None selected means all.

**Risk & Execution** — the settings that actually control your money:

| Setting | What it does | Sane starting point |
| --- | --- | --- |
| Max leverage | Multiplier cap per position. | 1–3x while learning |
| Trade allocation (%) | Share of the account committed per trade. | 5–10% |
| Confidence floor (%) | Minimum signal score required to trade. Higher = fewer, higher-quality trades. | 60–70 |
| Long / Short funding threshold (hourly %) | Funding levels beyond which longs (or shorts) become unattractive or attractive. Displayed as percentages; stored internally as decimals. | template default |
| Funding extreme K | For the funding/arb templates: how many times "normal" funding must be exceeded to count as extreme. | 1.5 |
| Minimum hold (bars) | Don't exit before this many candles have passed — stops nervous flip-flopping. A *bar*/*candle* is one time slice of the chart. | 3+ |
| Post-exit cooldown (bars) | Wait this many bars after an exit before re-entering the same market. | 2+ |
| Exit hysteresis score | How much the signal must weaken before an exit is honoured; prevents exiting on noise. | 50 |
| Stop loss (%) | Automatic exit at this loss. | 1–3% |
| Take profit (%) | Automatic exit at this gain. | usually 2× the stop |
| Trailing stop (%) | A stop that follows the price in your favour, locking in profit. | 1–2% |
| Execution mode | `manual`, `auto-confirm`, `auto`. **Currently descriptive only** — nothing auto-trades. | manual |
| Schedule | Free text, e.g. "every 4 hours". **Also descriptive only** — no scheduler runs it. | — |

These stop/target values are the same numbers used by the backtester *and* enforced on paper and live
positions. Trailing stops are monitored for paper positions but are unsupported for live positions.

---

## 11. Backtest Lab and Strategy Finder

### Backtest Lab

*Sidebar → Backtest.* Replays a strategy over historical Hyperliquid candles.

Inputs: **Strategy**, **Symbol**, **Interval** (candle length: 1m … 1d), **Initial Balance**,
**Start/End Date**. Under *Show advanced parameters*: **Maker Fee**, **Taker Fee**, **Order Type**
(`Taker` = fee + slippage, `Maker` = maker fee and no slippage — which assumes your resting order
always gets filled, so maker results are the optimistic case), and **Slippage %** with an
**Estimate live book** button that estimates current live-book slippage for your size.
Fees default to your wallet's actual Hyperliquid fee tier when available.

Results:

| Metric | Meaning |
| --- | --- |
| Total Return | Percentage gain/loss over the period. |
| Benchmark Return | What simply buying and holding the coin would have returned. **If your strategy loses to this, it is not adding value.** |
| Sharpe Ratio | Return per unit of volatility — reward vs. bumpiness. Roughly: <1 weak, 1–2 decent, >2 suspicious in crypto backtests. |
| Max Drawdown | Worst peak-to-trough fall in equity. The number that decides whether you could actually stomach it. |
| Win Rate | Share of trades that ended profitable. High win rate with tiny wins and huge losses is still a losing system. |
| Net / Gross Profit Factor | Total profit divided by total loss, after / before costs. Above 1 means profitable; the gap between the two shows how much fees and funding eat. |
| # Trades | Sample size. A dozen trades proves nothing. |
| Final Balance | End equity. |
| Avg Win / Avg Loss | Average size of winners vs. losers. |
| Confidence Floor / Leverage / Allocation | The risk settings the run used. |
| Final Signal | The strategy's stance on the last bar: LONG, SHORT or FLAT (no position). |
| Signal Mix | How many bars were long / short / flat. |

Charts: **Equity Curve** (account value over time), **Drawdown** (how far below the previous peak
you were, at every moment), **Price + Buy/Sell Signals** (candles with entries and exits marked),
**Cost Breakdown** (gross PnL → fees → funding → net PnL, plus the assumptions used) and the
**Trades** table with each round trip and its exit reason. **Activate as Paper Strategy** marks the
saved strategy as `manual` for paper use; it does not copy the tested settings back onto the saved
strategy.

A *candle* (OHLC bar) summarises one interval with its open, high, low and close prices.

### Strategy Finder

*Sidebar → Strategy Finder.* Tries many parameter combinations across many templates and — crucially
— reports whether the winner is real or luck. Test enough combinations and something always looks
brilliant on past data; that illusion is *overfitting*, and this page is built to expose it.

How it avoids fooling you: **anchored walk-forward** validation. History is split into **folds**;
for each fold the best parameters are chosen on the earlier "training" slice (*in-sample*) and then
judged only on the later, untouched slice (*out-of-sample*). Out-of-sample numbers are the only ones
worth believing.

Inputs: **Symbol**, **Interval**, **Start/End date**, **Folds** (2–6 splits), **Grid preset**
(`Coarse` = fewer combinations, recommended; `Standard` = exhaustive and slow),
**Min in-sample trades** (ignore candidates with too few trades to mean anything),
**Initial balance**, the **Templates** to include, and the same fee/slippage settings.
The page estimates the workload before you start and polls until the job finishes.

The three verdict cards:

1. **Did optimising help at all?** — selected strategies' compounded return vs. buy-and-hold over
   the same test windows.
2. **Is the winner distinguishable from noise?** — the **Deflated Sharpe Ratio (DSR)**, which
   penalises the Sharpe ratio for the number of combinations tried. "Not significant" means the
   winner is within what pure luck would produce.
3. **Does in-sample ranking predict out-of-sample ranking?** — a **rank correlation**. At or below
   zero, past leaderboards tell you nothing about the future, so treat the table below as history,
   not a forecast.

The candidate table ranks by median out-of-sample per-bar Sharpe and also shows the annualised
Sharpe, median and mean out-of-sample return, **Overfit gap** (how much better a candidate looked in
training than in testing — large gaps are red flags), out-of-sample trade counts, folds with trades,
and the full-range winner. A **regime breakdown** splits results by
funding and volatility conditions, so you can see whether an edge only existed in one market mood.

---

## 12. Going live: the three gates

Real orders require **all three** of these, and each is checked on every live open and close.
If one is off, the error tells you which:

1. `LIVE_TRADING=true` in `.env` (then restart the backend) — the process-wide switch.
2. The wallet's **live trading** permission enabled: `POST /api/portfolio/live` with
   `{"walletId": "…", "enabled": true}`. There is no button for this in the UI on purpose.
3. `mode = live` on the individual trade — the **Execution mode** selector on the signal card, plus
   your master password in the confirmation dialog.

Before you ever do this:

- Paper trade for at least a week and read your Journal honestly.
- Consider `HYPERLIQUID_NETWORK=testnet` first: same app, fake money.
- Start with tiny size and 1–2x leverage.
- Know that live entries set the asset's leverage on Hyperliquid immediately before the market
  order, clamped to that market's maximum; if the leverage update is rejected, the order is aborted.
- Never commit `.env`, private keys or `app/backend/data/*.db` to Git.
- Know where the kill switch is before you need it.

---

## 13. Alerts and Journal

**Alerts** (*sidebar, with an unread badge*) — notifications by type: `signal` (new suggestion),
`position` (opened/closed), `risk` (limit breached), `reconciliation`, `protective_exit`
(a stop, target or trailing stop fired) and `kill_switch`. Severity is `info`, `success`, `warning`
or `error`. Filter All/Unread, mark individually or all read.

**Journal** — one entry per closed trade: symbol, side, leverage, entry, exit, size, fees, net PnL
and, when present, a **Reflection** note reviewing how the trade actually went. This is the honest
record of your results; it is also the main reason paper trading is worth doing properly.

---

## 14. Glossary

**Agent** — one specialised analyst in the app (Market, Funding, OrderBook, Sentiment, News). Each
looks at one kind of evidence; a strategy combines the ones you enable.

**Allocation** — the share of your account committed to a single trade, in percent.

**API agent wallet** — a Hyperliquid key approved to trade an account but not to withdraw from it.
The safe way to let software trade for you.

**Arbitrage ("arb")** — profiting from a price or fee difference between two related things,
ideally with little directional risk.

**ATR (Average True Range)** — average size of recent price swings; a volatility measure.

**Backtest** — replaying a strategy over past data to see how it would have done. Always optimistic.

**Bar / candle / OHLC** — one time slice of the chart, summarised by its open, high, low and close
prices. A "1h candle" covers one hour.

**Basis** — the gap between a perpetual contract's price and the underlying coin's spot price.

**Benchmark return** — what buying and holding the coin would have returned over the same period.
The bar any strategy must clear to be worth running.

**Bollinger Bands** — lines drawn a set distance above and below a moving average; price near a band
is considered stretched.

**Confidence** — the app's own 0–100 score for a signal's strength. Not a probability.

**Confidence floor** — the minimum confidence required before a trade is allowed.

**Cooldown (bars)** — enforced wait after an exit before the same market may be re-entered.

**Deflated Sharpe Ratio (DSR)** — a Sharpe ratio adjusted for how many strategies you tested.
Answers "would this look this good by chance?".

**Delta neutral** — positioned so that price direction barely affects you; used to harvest funding.

**Donchian channel** — the highest high and lowest low over the last N bars; breaking out of it is a
classic entry trigger.

**Drawdown** — how far equity has fallen from its previous peak. *Max drawdown* is the worst such
fall, and the most honest measure of pain.

**EMA / SMA (moving averages)** — the average price over the last N bars, used to define trend.
EMA weights recent bars more heavily; SMA weights all equally.

**Equity** — total account value: cash plus the current value of open positions.

**Equity curve** — a chart of equity over time.

**Exit hysteresis** — how much a signal must weaken before an exit is honoured, so noise does not
close good trades.

**Exit reason** — why a trade closed: `signal`, `stop_loss`, `take_profit`, `trailing_stop`, or
`end_of_backtest`.

**Fee tier** — your personal maker/taker fee rates on the exchange, based on volume and discounts.

**Flat** — holding no position.

**Flatten** — close all open positions.

**Fold** — one training/testing split of history in walk-forward validation.

**Funding rate** — the recurring payment between longs and shorts on a perpetual, which keeps its
price near spot. Positive: longs pay shorts. Negative: shorts pay longs.

**Funding extreme K** — how many times "normal" funding must be exceeded before the funding
strategies call it extreme.

**Grid preset** — how many parameter combinations Strategy Finder tries: `coarse` (fewer, faster) or
`standard` (many, slow).

**Gross vs. net** — before vs. after fees and funding costs.

**Hyperliquid** — the crypto exchange this app trades on, offering perpetual futures and spot.
*Mainnet* is real money; *testnet* is a practice network with fake money.

**In-sample / out-of-sample** — data used to pick parameters vs. data held back to judge them.
Only out-of-sample results carry information about the future.

**Interval** — candle length used for analysis or backtesting (1m, 5m, 15m, 1h, 4h, 1d).

**Kill switch** — emergency stop: revoke live permission, cancel resting orders, close positions.

**Leverage** — borrowed size, expressed as a multiple. 5x means a 1% price move changes your money
by 5%. Multiplies losses too, and creates liquidation risk.

**Limit order** — an order at a price you choose; it waits until the market reaches it.

**Liquidation** — forced closure by the exchange when margin runs out. Typically loses the whole
margin on that position.

**Liquidation wick** — a violent, brief price spike caused by cascading liquidations; some
mean-reversion strategies hunt these.

**LLM (large language model)** — the AI (e.g. GPT, Claude) that can write a signal's reasoning.
Optional, costs money per call, needs an API key.

**Long** — a position that profits when price rises.

**Maker / taker** — a maker order rests in the order book and pays lower fees; a taker order fills
immediately against existing orders and pays more.

**Margin** — collateral set aside for a position.

**Mark price** — the exchange's reference price used to value positions and decide liquidations.

**Market order** — an order filled immediately at whatever price is available. What this app sends.

**Mean reversion** — the idea that stretched prices tend to snap back toward the average.

**Minimum hold (bars)** — the shortest time a position must be kept before exiting.

**Momentum** — the idea that moves tend to continue in the same direction.

**Notional** — the face value of a position (size × price): how much market you control, which with
leverage exceeds your balance.

**Open interest (OI)** — the total value of outstanding contracts on a market. Rising OI alongside
rising price suggests new money entering.

**Order book** — the live list of resting buy and sell orders. Its shape hints at short-term
pressure and determines your slippage.

**Overfitting** — tuning a strategy so tightly to past data that it captures noise rather than a
real edge, then failing in the future. The single biggest risk in this whole app.

**Paper trading** — simulated trading with no real orders and no real money. The app's default mode.

**Perpetual future ("perp")** — a contract tracking a coin's price with no expiry date, kept honest
by funding payments. Allows shorting and leverage; you never own the coin.

**PnL** — profit and loss. *Unrealized*: on open positions. *Realized*: locked in after closing.

**Position** — an open trade: symbol, side, size, leverage, entry price.

**Profit factor** — total profits divided by total losses. Above 1 = profitable.

**Rank correlation** — whether the leaderboard from training data matches the leaderboard from
test data. Zero or negative means the training leaderboard is worthless as a forecast.

**Reconciliation** — comparing the app's records against the exchange's, to catch mismatches.

**Reduce-only order** — an order that can only shrink or close a position, never open a new one.
Protective stops are placed this way.

**Regime** — the prevailing market condition (e.g. high vs. low volatility, positive vs. negative
funding). Many edges only exist in one regime.

**RSI (Relative Strength Index)** — a 0–100 momentum gauge; above 70 is conventionally "overbought",
below 30 "oversold".

**Seasonality** — a repeating pattern tied to the clock or calendar, e.g. a specific hour of the day.

**Sharpe ratio** — return divided by volatility: how much reward per unit of bumpiness. Higher is
better; very high values in a backtest usually mean overfitting.

**Short** — a position that profits when price falls.

**Signal** — the app's suggestion for one market: BUY, SELL or HOLD, with size, stop, target,
confidence and reasoning.

**Slippage** — the difference between the price you expected and the price you got. Grows with your
order size and with thin order books.

**Spot** — buying the actual coin, no leverage, no funding.

**Stop loss** — a preset exit that caps the loss on a trade.

**Take profit** — a preset exit that banks a gain.

**Token (LLM)** — the billing unit for AI text, roughly ¾ of a word. Distinct from a crypto token.

**Trailing stop** — a stop that follows price in your favour, locking in profit as it moves. Its
**watermark** is the best price reached so far, from which the trailing distance is measured.

**Trend following** — trading in the direction of an established move.

**USDC** — a dollar-pegged stablecoin; the collateral currency on Hyperliquid.

**Volatility** — how much price moves around. More volatility means more opportunity and more risk.

**Volume** — how much was traded in a period. Higher volume means easier entry and exit.

**Walk-forward validation** — repeatedly choosing parameters on an earlier window and testing them
on the next, untouched window. The honest way to evaluate a strategy.

**Win rate** — the share of trades that were profitable. Meaningless without knowing average win
versus average loss size.

---

## 15. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Port 8000 already in use | Set `PORT=8001` in `.env` and `VITE_API_URL=http://localhost:8001` in `app/frontend/.env`. |
| No signals appear | Check the backend is running (`cd app && python -m backend.main`); untick *Use LLM* if you have no API key. |
| "Select an active wallet before accepting a signal" | Pick a wallet in the sidebar; add one on the Wallets page first. |
| Live action rejected | One of the three gates is off — the error names it. See [section 12](#12-going-live-the-three-gates). |
| Reconciliation says `diverged` | Read the listed divergences, then reconcile again. If you do not understand the mismatch, use the kill switch. |
| Reconciliation says `unavailable` | The exchange could not be reached; check connectivity and `HYPERLIQUID_NETWORK`. |
| Strategy search takes forever | Use the `Coarse` grid preset, fewer templates, a shorter date range or a longer interval. |
| Database errors / want a clean slate | Delete `app/backend/data/*.db`. This erases paper positions, signals, alerts, journal and wallets. |

Development commands, from the repository root:

```bash
ruff check app/backend
pytest app/backend/tests
npm --prefix app/frontend run lint
npm --prefix app/frontend run build
```
