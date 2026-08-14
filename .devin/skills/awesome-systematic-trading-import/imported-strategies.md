# Imported strategies log

Tracks strategies ported from
https://github.com/paperswithbacktest/awesome-systematic-trading into
TradingAgents via the `awesome-systematic-trading-import` skill, so future
runs don't duplicate work. Append one entry per strategy when you finish
step 3 of the skill.

## Already in the project before this log existed

See `.devin/skills/fmz-strategy-import/imported-strategies.md` for the full
pre-existing template roster (`momentum_breakout`, `mean_reversion`,
`funding_rate_arb`, `hype_delta_neutral`, `trend_following`,
`scalp_momentum`, `news_event`, `basis_arbitrage`, `custom`, plus everything
ported from fmzquant/strategies). Not sourced from
awesome-systematic-trading.

## Ported from paperswithbacktest/awesome-systematic-trading

| Template slug | Source strategy | Notes |
| --- | --- | --- |
| `time_series_momentum` | [Time Series Momentum Effect](https://quantpedia.com/strategies/time-series-momentum-effect/) ([impl](https://github.com/paperswithbacktest/awesome-systematic-trading/blob/main/static/strategies/time-series-momentum-effect.py)) | Original strategy trades ~60 futures/currencies/bonds/equity indices, going long/short each asset based on the sign of its trailing 12-month return with inverse-volatility position sizing and monthly rebalancing. Collapsed to a single symbol: added a `tsmomRet` column (`close` vs. `close` 60 bars ago, shifted 1) to `_prepare_candles()`; sign of `tsmomRet` drives long (score 70) / short (score 30) / flat (NaN warmup), plus the usual funding tilt. Vol-based position sizing was dropped (this project sizes via `allocation`/`leverage`, not per-signal vol targeting). |
| `overnight_seasonality_btc` | [Intraday Seasonality in Bitcoin](https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin/) ([impl](https://github.com/paperswithbacktest/awesome-systematic-trading/blob/main/static/strategies/intraday-seasonality-in-bitcoin.py)) | Original strategy opens a long BTC position at 22:00 UTC and closes it at 00:00 UTC (2-hour holding window), long-only. Ported directly since it's already single-symbol: branch checks `df.index[idx].hour in (22, 23)` (bar timestamps are UTC per `_prepare_candles()`) and scores 80 (long) during that window, `0` (flat) otherwise — never scores bearish, so it only ever produces long or flat signals, matching the original's long-only design. Works best on `1h` bars; coarser intervals (4h/1d) will rarely or never land exactly on the window. |

## Good next candidates (not yet ported)

Fill in / update this list as you scan the awesome-systematic-trading
README. Examples worth investigating next time:
- [Short Term Reversal Effect in Stocks](https://quantpedia.com/strategies/short-term-reversal-in-stocks/)
  — cross-sectional (long losers/short winners across 100 stocks weekly).
  Single-symbol analogue: z-score of the trailing 5-bar return vs. its own
  rolling distribution, fade extremes. Distinguish clearly from the
  existing `mean_reversion` template (which uses RSI + Bollinger Bands) by
  keying purely off cumulative return, per the paper's method.
- [Volatility Risk Premium Effect](https://quantpedia.com/?s=volatility+risk+premium)
  — genuinely needs an options chain (short variance swap proxy); only
  attempt if a funding-rate or realized-vs-implied-vol proxy can be
  justified, otherwise skip.
- [FX Carry Trade](https://quantpedia.com/strategies/fx-carry-trade/) /
  [Dollar Carry Trade](https://quantpedia.com/strategies/dollar-carry-trade/)
  — carry direction already resembles this project's existing
  `funding_rate_arb`/`basis_arbitrage` templates (fade funding extremes);
  check for meaningful differentiation before porting as a new template.
- [Trend-following Effect in Stocks](https://quantpedia.com/strategies/trend-following-effect-in-stocks/)
  — likely overlaps heavily with the existing `trend_following` template;
  read closely for a differentiating rule (e.g. different lookback/filter)
  before adding a near-duplicate.

## Skipped as out of scope

- Cross-sectional multi-asset strategies with no reasonable single-symbol
  analogue (large equity universes requiring market cap/fundamental data,
  sector rotation, pairs trading across two different tickers) — this
  project's signal model is one symbol, long/short/flat, not a ranked
  portfolio.
- Strategies requiring data this project doesn't ingest: options chains/
  implied vol surfaces, company filings text, ESG scores, earnings
  calendars, futures term-structure/roll data.
