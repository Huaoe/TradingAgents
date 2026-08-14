---
name: fmz-strategy-import
description: Port a classic strategy from fmzquant/strategies (github.com/fmzquant/strategies) into TradingAgents as a new strategy template (strategy_store.py + backtest.py + frontend template pickers)
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
[fmzquant/strategies](https://github.com/fmzquant/strategies) (a large
multi-language — JS/Python/C++/PineScript/Blockly/MyLanguage — collection of
strategies for the FMZ trading platform) and porting its *core idea* into
this project (TradingAgents) as a new backtestable strategy template.

Do NOT literally translate FMZ platform code (it depends on FMZ's own
`exchange.GetTicker()`-style runtime, multi-exchange plumbing, UI controls,
etc.). Instead: read the strategy's README/description to understand its
trading logic, then re-implement that logic idiomatically using this
project's existing indicators and conventions.

Read `imported-strategies.md` in this skill's directory first — it tracks
which strategies have already been ported so you don't duplicate work, and
lists good next candidates.

## 1. Pick a candidate strategy

- Browse https://github.com/fmzquant/strategies (the root `README.md` lists
  every strategy with a short Chinese/English description, grouped by
  language: JavaScript, Python, C++, PineScript, Blockly, MyLanguage).
- Skip anything that's pure infrastructure/plumbing for the FMZ platform
  (websocket accelerators, fund-transfer tools, UI parameter test rigs,
  exchange-specific arbitrage that needs simultaneous multi-exchange order
  routing we don't support, Blockly-only strategies with no readable logic).
- Prefer strategies with a clear, self-contained, symbol-local trading rule:
  breakout systems, mean-reversion/oscillator systems, trend-following,
  grid/DCA, volatility band systems, funding/basis arbitrage variants, etc.
  These map cleanly onto a single-symbol perp signal.
- `webfetch` the strategy's `.md` file (e.g.
  `https://github.com/fmzquant/strategies/blob/master/<name>.md` — use the
  raw URL `https://raw.githubusercontent.com/fmzquant/strategies/master/<name>.md`
  for cleaner text) to read its actual entry/exit rules and parameters.

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
    `donchianHigh`/`donchianLow`, `dtHH`/`dtHC`/`dtLC`/`dtLL`, ...). If your
    strategy needs a new indicator, add a column here (use `.shift(1)` for
    anything that must not look ahead into the current bar).
  - `_signal_for_bar(df, idx, strategy)` is an `if/elif` chain keyed on
    `strategy.get("template", "custom").replace("_", "-")` (so a
    `template` slug of `my_new_strategy` in `TEMPLATES` must match an
    `elif template == "my-new-strategy":` branch here). Each branch computes
    a `score` around a 50 baseline (higher = more bullish), optionally adds
    `funding_score()` for a funding-rate tilt, and the caller converts score
    to -1/0/1 using `confidence_floor` from `riskConfig`:
    `score >= confidence_floor` → long (1); `score <= 100 - confidence_floor`
    → short (-1); otherwise flat (0). Return `0` directly for "no signal
    today" cases (e.g. indicator still `NaN`, price inside a neutral zone).
    Reuse helpers already in scope: `trend_up`/`trend_down`, `bound_score()`,
    `rsi_score()`, `funding_score()`.
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
   description crediting the original idea (e.g. "Adapted from FMZ's ...
   strategy."), reasonable `agents`, `llmProvider`/`llmModel`/`llmMode`
   matching the style of neighboring entries, and a `riskConfig` with a
   `confidenceFloor` chosen so your score thresholds actually trigger both
   long and short (see the scoring convention above — e.g. score 70/30 needs
   `confidenceFloor <= 70`).
2. If needed, add new indicator column(s) to `_prepare_candles()`.
3. Add the matching `elif template == "<kebab-slug>":` branch to
   `_signal_for_bar()`.
4. Add matching entries to `TEMPLATE_CARDS` (Strategies.tsx) and
   `TEMPLATE_DEFAULTS` (StrategyEditor.tsx) using the same `snake_slug`.
5. Append a line to `imported-strategies.md` in this skill directory noting
   the FMZ source strategy name/URL, the new `template` slug, and a one-line
   summary of the mapping/simplifications you made.

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
n = 200
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

A healthy result has a non-trivial mix of longs/shorts/flats (not all 0, not
constantly firing every bar) and no exceptions.

## 5. Report

Summarize: which FMZ strategy was the inspiration (with link), the new
template slug/id, the mapping decisions and simplifications made, and the
verification output.
