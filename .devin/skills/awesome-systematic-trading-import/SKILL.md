---
name: awesome-systematic-trading-import
description: Port an academic/institutional strategy from paperswithbacktest/awesome-systematic-trading (github.com/paperswithbacktest/awesome-systematic-trading) into TradingAgents as a new strategy template (strategy_store.py + backtest.py + frontend template pickers)
allowed-tools:
  - read
  - grep
  - glob
  - edit
  - write
  - exec
  - webfetch
  - web_search
  - find_file_by_name
triggers:
  - user
  - model
---

You are extracting/adapting ONE strategy at a time from the community repo
[paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading)
(a curated list of ~40+ academic/institutional trading strategies, each with
a Quantpedia writeup and a reference QuantConnect (`QCAlgorithm`) Python
implementation) and porting its *core idea* into this project
(TradingAgents) as a new backtestable strategy template.

Do NOT literally translate the QuantConnect code (it depends on QC's own
universe-selection, multi-asset portfolio, `SetHoldings`/`Schedule.On`
runtime, and most strategies there trade baskets of 10-100+ stocks/futures
rebalanced monthly). Instead: read the strategy's short Quantpedia summary
(top-of-file comment block) to understand the trading rule, then
re-implement its *single-symbol, single-position* analogue idiomatically
using this project's existing indicators and conventions. This project only
supports one perp/spot symbol per strategy in long/short/flat form — there
is no cross-sectional universe or portfolio weighting — so cross-sectional
"long the top decile / short the bottom decile across N assets" strategies
must be reframed as a time-series signal on a single symbol (e.g. "sign of
trailing return" instead of "rank across the universe").

Read `imported-strategies.md` in this skill's directory first — it tracks
which strategies have already been ported so you don't duplicate work, and
lists good next candidates.

## 1. Pick a candidate strategy

- `webfetch` `https://raw.githubusercontent.com/paperswithbacktest/awesome-systematic-trading/main/README.md`
  and look at the `## Strategies` section (grouped by asset class: Cryptos,
  Currencies, Commodities, Equities, Bonds+X combos). Each row has a Title,
  Sharpe Ratio, Volatility, Rebalancing cadence, a link to the reference
  implementation under `static/strategies/<slug>.py`, and a link to the
  source paper/Quantpedia page.
- `webfetch` the reference implementation, e.g.
  `https://raw.githubusercontent.com/paperswithbacktest/awesome-systematic-trading/main/static/strategies/<slug>.py`
  — the top-of-file comment block is a concise Quantpedia summary of the
  actual trading rule; the QC code below it is mostly universe-selection
  and portfolio-weighting boilerplate you should ignore.
- Prefer strategies whose core signal is naturally single-symbol
  time-series (time-series momentum, short-term reversal, trend-following,
  volatility risk premium, seasonality/time-of-day effects, carry). Skip or
  heavily simplify strategies whose entire edge comes from cross-sectional
  ranking across a large universe (e.g. "top 100 market cap, long top decile
  momentum / short bottom decile") — only port these if you can articulate a
  reasonable single-symbol analogue (e.g. rank vs. own history instead of
  vs. other assets) and note the simplification clearly.
- Skip pure options/derivatives strategies that need an options chain
  (dispersion trading, most volatility-risk-premium variance-swap
  strategies) unless there's a clean proxy using spot/perp OHLCV + funding
  rate (e.g. use `fundingRate` as a crude vol/carry-premium proxy instead of
  actual implied vol).
- Skip strategies needing fundamental/alternative data this project doesn't
  have (market cap, filings text, ESG scores, earnings calendars).

## 2. Understand the target architecture (read these files first)

- `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/backend/models/strategy.py" />`
  — `RiskConfig` fields available to every strategy: `longFundingThreshold`,
  `shortFundingThreshold`, `leverage`, `allocation`, `confidenceFloor`. Don't
  add new risk-config fields unless truly necessary (the UI doesn't expose
  extra fields per-template today).
- `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/backend/services/strategy_store.py" />`
  — `TEMPLATES: list[dict]` is the source of truth for template metadata
  (id, name, description, `template` slug, default `agents`, LLM
  provider/model/mode, `riskConfig`). Seeding is idempotent by `id`, so
  appending a new entry is enough to make it show up in the DB on next
  startup — no migration needed.
- `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/backend/services/backtest.py" />`
  — this is where template-specific signal logic actually lives:
  - `_prepare_candles()` computes shared indicator columns on the OHLCV
    dataframe (`sma20`, `sma50`, `upperBB`/`lowerBB`, `rsi14`, `atr14`,
    `donchianHigh`/`donchianLow`, `dtHH`/`dtHC`/`dtLC`/`dtLL`, `emaHigh`/
    `emaLow`/`emaSlow`, `tsmomRet`, ...). If your strategy needs a new
    indicator (e.g. a different lookback return, a rolling z-score, an
    hour-of-day feature via `df.index[idx].hour`), add a column here (use
    `.shift(1)` for anything that must not look ahead into the current bar
    — time-of-day features derived only from the index timestamp don't need
    a shift since they carry no future price information).
  - `_signal_for_bar(df, idx, strategy)` is an `if/elif` chain keyed on
    `strategy.get("template", "custom").replace("_", "-")` (so a
    `template` slug of `my_new_strategy` in `TEMPLATES` must match an
    `elif template == "my-new-strategy":` branch here). Each branch computes
    a `score` around a 50 baseline (higher = more bullish), optionally adds
    `funding_score()` for a funding-rate tilt, and the caller converts score
    to -1/0/1 using `confidence_floor` from `riskConfig`:
    `score >= confidence_floor` → long (1); `score <= 100 - confidence_floor`
    → short (-1); otherwise flat (0). Return `0` directly for "no signal
    today" cases (e.g. indicator still `NaN`, outside a time window, price
    inside a neutral zone). Reuse helpers already in scope:
    `trend_up`/`trend_down`, `bound_score()`, `rsi_score()`,
    `funding_score()`. A strategy can be long-only (e.g. a seasonality
    window) by only ever assigning a bullish score or returning `0` — never
    assign a bearish score — so it never fires short.
  - `run_backtest()` drives `_compute_signals()` over the whole dataframe —
    you normally don't need to touch this.
- Live trading path `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/backend/services/signal_engine.py" />`
  is intentionally template-agnostic (same generic trend+funding+orderbook
  rule for every template, live). Existing precedent is to leave it alone —
  only the backtester differentiates by template. Don't add per-template
  branching there unless the user explicitly asks for it.
- Frontend surfaces (cosmetic, must stay in sync with the backend template
  slug):
  - `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/frontend/src/pages/Strategies.tsx" />`
    — `TEMPLATE_CARDS` array (template gallery cards).
  - `<ref_file file="/home/huaoe/Documents/Projects/TradingAgents/app/frontend/src/pages/StrategyEditor.tsx" />`
    — `TEMPLATE_DEFAULTS` record (default agents/riskConfig prefilled when a
    template is picked).

## 3. Implement

1. Add one entry to `TEMPLATES` in `strategy_store.py`:
   `id: "template-<kebab-slug>"`, `template: "<snake_slug>"`, a short
   description crediting the original idea and repo (e.g. "Adapted from
   paperswithbacktest/awesome-systematic-trading's ... effect."), reasonable
   `agents`, `llmProvider`/`llmModel`/`llmMode` matching the style of
   neighboring entries, and a `riskConfig` with a `confidenceFloor` chosen
   so your score thresholds actually trigger (see the scoring convention
   above — e.g. score 70/30 needs `confidenceFloor <= 70`; a long-only
   strategy that only ever scores 80 or returns 0 needs `confidenceFloor <=
   80` to actually fire).
2. If needed, add new indicator column(s) to `_prepare_candles()`.
3. Add the matching `elif template == "<kebab-slug>":` branch to
   `_signal_for_bar()`.
4. Add matching entries to `TEMPLATE_CARDS` (Strategies.tsx) and
   `TEMPLATE_DEFAULTS` (StrategyEditor.tsx) using the same `snake_slug`.
5. Append a line to `imported-strategies.md` in this skill directory noting
   the source strategy name/URL, the new `template` slug, and a one-line
   summary of the mapping/simplifications you made (especially how you
   collapsed a cross-sectional/multi-asset rule into a single-symbol one).

## 4. Verify

Run these before considering the work done (adjust the venv path if it has
moved — locate it with `find <repo-root> -maxdepth 3 -iname ".venv"` if
unsure):

```bash
# Backend: compiles
cd <repo-root>/app && <repo-root>/.venv/bin/python -m py_compile \
  backend/services/strategy_store.py backend/services/backtest.py

# Backend: sanity-check the new template on synthetic OHLCV data
cd <repo-root>/app && <repo-root>/.venv/bin/python -c "
import numpy as np, pandas as pd
from backend.services.backtest import _prepare_candles, _signal_for_bar

np.random.seed(0)
n = 400
base = 100 + np.cumsum(np.random.randn(n))
candles = []
t0 = 1700000000000
for i in range(n):
    o = base[i]
    c = o + np.random.randn() * 0.5
    h = max(o, c) + abs(np.random.randn() * 0.3)
    l = min(o, c) - abs(np.random.randn() * 0.3)
    candles.append({'time': t0 + i * 3600000, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': abs(np.random.randn() * 1000)})

df = _prepare_candles(candles)
strat = {'template': '<snake_slug>', 'riskConfig': {'confidenceFloor': 60}}
sigs = [_signal_for_bar(df, i, strat) for i in range(len(df))]
print('longs=', sigs.count(1), 'shorts=', sigs.count(-1), 'flat=', sigs.count(0))
"

# Confirm the template list grew and ids are unique
cd <repo-root>/app && <repo-root>/.venv/bin/python -c "
from backend.services.strategy_store import TEMPLATES
ids = [t['id'] for t in TEMPLATES]
assert len(ids) == len(set(ids)), 'duplicate template id!'
print(len(TEMPLATES), ids)
"

# Frontend typechecks
cd <repo-root>/app/frontend && npx tsc --noEmit
```

A healthy result depends on the strategy's nature: directional strategies
(momentum, reversal, trend) should show a non-trivial mix of longs/shorts/
flat (not all 0, not constantly firing every bar); intentionally long-only
strategies (e.g. seasonality windows) should show longs + flat only, with
`shorts == 0`, and the long count roughly matching the expected fraction of
bars inside the window. No exceptions either way.

## 5. Report

Summarize: which awesome-systematic-trading strategy was the inspiration
(with link to its Quantpedia page and reference implementation), the new
template slug/id, the mapping decisions and simplifications made
(especially any cross-sectional → single-symbol reframing), and the
verification output.
