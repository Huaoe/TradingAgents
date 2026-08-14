# Imported strategies log

Tracks strategies ported from https://github.com/fmzquant/strategies into
TradingAgents via the `fmz-strategy-import` skill, so future runs don't
duplicate work. Append one entry per strategy when you finish step 3 of the
skill.

## Already in the project before this log existed

These were part of the original `TEMPLATES` list in `strategy_store.py` and
are NOT sourced from fmzquant/strategies (kept here just so the full
template roster is visible at a glance):

- `momentum_breakout` — Momentum Breakout
- `mean_reversion` — Mean Reversion
- `funding_rate_arb` — Funding Rate Arb
- `hype_delta_neutral` — HYPE Delta Neutral
- `trend_following` — Trend Following
- `scalp_momentum` — Scalp Momentum
- `news_event` — News Event
- `basis_arbitrage` — Basis Arbitrage
- `custom` — Custom (blank template, always keep last in the UI list)

## Ported from fmzquant/strategies

| Template slug | FMZ source idea | Notes |
| --- | --- | --- |
| `grid_trading` | Classic FMZ grid trading strategies (buy low/sell high within a range grid) | Simplified to directional long/short bias using the 20-bar Donchian range position (bottom 20% = long, top 20% = short) instead of true multi-level grid orders, since this project's signal model is single-position long/short/flat rather than a resting-order grid. |
| `dual_thrust` | Dual Thrust (iconic FMZ/quant-community range-breakout system) | Classic formula: `Range = max(HH-LC, HC-LL)` over a 4-bar lookback, `upper = open + k1*Range`, `lower = open - k2*Range`, `k1=k2=0.5`. Long above upper band, short below lower band. |
| `turtle_breakout` | Turtle Trading system (Donchian channel breakout) | 20-bar Donchian channel breakout (long on new N-bar high, short on new N-bar low), ATR-based stop distance already available via existing `atr14` column for future extension. |
| `ema_bands_trend_catch` | [EMA-bands-leledc-bollinger-bands-trend-catching-strategy](https://github.com/fmzquant/strategies/blob/master/EMA-bands-leledc-bollinger-bands-trend-catching-strategy.md) | EMA of highs/lows as a middle band with a 200-period close EMA filter, plus counter-trend Bollinger Band/RSI exhaustion signals (close back inside the bands from an overbought/oversold RSI extreme). Adapted to the project's long/short/flat per-bar signal model. |

## Good next candidates (not yet ported)

Fill in / update this list as you scan the fmzquant README. Examples worth
investigating next time:
- ahr999 DCA index strategy (accumulation strategy based on a valuation
  index) — would need a new "DCA" execution style, bigger lift.
- Martingale-style position-sizing strategies — risky, needs careful mapping
  onto `allocation`/`leverage`, discuss with the user before porting since
  martingale sizing conflicts with the fixed-allocation risk model here.

## Skipped as out of scope

- Multi-exchange arbitrage/hedging tools (pair trading across exchanges,
  fund transfer plugins, websocket accelerators) — require infrastructure
  this project doesn't have (multi-exchange execution).
- Pure UI/testing/demo strategies (parameter test rigs, interactive control
  demos) — no trading logic to port.
