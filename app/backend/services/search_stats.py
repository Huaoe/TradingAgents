"""Statistics for strategy search: selection bias, overfitting, and regimes.

A parameter sweep always produces a winner.  The point of this module is to
answer whether that winner is distinguishable from the best of N random draws,
which is what the raw Sharpe ratio of a selected strategy cannot tell you.

References:
    Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio: Correcting for
    Selection Bias, Backtest Overfitting and Non-Normality".
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

# Euler-Mascheroni constant, used by the expected-maximum-Sharpe estimator.
_EULER_GAMMA = 0.5772156649015329

_NORMAL = NormalDist()


def per_bar_returns(equity_values: list[float]) -> list[float]:
    """Per-bar simple returns of an equity curve, dropping non-finite values."""
    if len(equity_values) < 2:
        return []
    series = pd.Series([float(v) for v in equity_values], dtype=float)
    returns = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    return [float(r) for r in returns]


def per_bar_sharpe(returns: list[float]) -> float | None:
    """Non-annualised Sharpe ratio: mean(r) / std(r, ddof=1).

    The deflated Sharpe ratio compares a candidate's Sharpe against the
    distribution of Sharpes across trials, so every input to it has to be in
    the same units.  Per-bar is the natural choice because the number of
    observations ``T`` enters the formula directly.
    """
    if len(returns) < 3:
        return None
    series = pd.Series(returns, dtype=float)
    std = float(series.std(ddof=1))
    if not math.isfinite(std) or std < 1e-12:
        return None
    sharpe = float(series.mean()) / std
    return sharpe if math.isfinite(sharpe) else None


def annualise_sharpe(per_bar: float, periods_per_year: float) -> float:
    """Scale a per-bar Sharpe ratio to annualised units for display."""
    return float(per_bar * math.sqrt(periods_per_year))


def expected_max_sharpe(trial_sharpes: list[float]) -> float | None:
    """Expected maximum per-bar Sharpe across ``N`` trials of zero true skill.

    ``SR0 = sqrt(V) * ((1 - gamma) * Z_inv(1 - 1/N) + gamma * Z_inv(1 - 1/(N*e)))``

    where ``V`` is the variance of the per-bar Sharpe ratios observed across
    the ``N`` trials.  This is the bar a selected strategy has to clear before
    its Sharpe means anything: run enough variants and one of them reaches
    ``SR0`` on noise alone.
    """
    finite = [float(s) for s in trial_sharpes if s is not None and math.isfinite(float(s))]
    n_trials = len(finite)
    if n_trials < 2:
        return None
    variance = float(np.var(finite, ddof=1))
    if not math.isfinite(variance) or variance <= 0.0:
        return None
    quantile_a = _NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    quantile_b = _NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    expected = math.sqrt(variance) * (
        (1.0 - _EULER_GAMMA) * quantile_a + _EULER_GAMMA * quantile_b
    )
    return float(expected) if math.isfinite(expected) else None


def deflated_sharpe_ratio(
    selected_returns: list[float],
    trial_sharpes: list[float],
) -> dict[str, Any]:
    """Probability that the selected candidate's true Sharpe ratio exceeds zero.

    ``DSR = Z[ (SR - SR0) * sqrt(T - 1)
               / sqrt(1 - skew * SR + (kurtosis - 1) / 4 * SR^2) ]``

    ``SR`` is the selected candidate's per-bar Sharpe, ``SR0`` the expected
    maximum across the trials that produced it, ``T`` the number of return
    observations, ``skew`` and ``kurtosis`` the sample skewness and the
    non-excess kurtosis of those returns.  The non-normality terms matter here:
    trading returns are skewed and fat-tailed, which inflates a plain Sharpe.

    Returns a dict with the DSR, its inputs, and ``significant`` at the
    conventional 0.95 level.  ``dsr`` is ``None`` when it cannot be computed,
    with ``reason`` naming the reason -- never a fabricated number.
    """
    result: dict[str, Any] = {
        "dsr": None,
        "significant": False,
        "observedSharpe": None,
        "expectedMaxSharpe": None,
        "trials": len([s for s in trial_sharpes if s is not None]),
        "observations": len(selected_returns),
        "skew": None,
        "kurtosis": None,
        "reason": None,
    }

    observed = per_bar_sharpe(selected_returns)
    if observed is None:
        result["reason"] = "not enough return observations to estimate a Sharpe ratio"
        return result
    result["observedSharpe"] = observed

    expected_max = expected_max_sharpe(trial_sharpes)
    if expected_max is None:
        result["reason"] = "need at least two trials with varying Sharpe ratios to deflate"
        return result
    result["expectedMaxSharpe"] = expected_max

    series = pd.Series(selected_returns, dtype=float)
    observations = len(series)
    if observations < 4:
        result["reason"] = "need at least four return observations for skew and kurtosis"
        return result
    skew = float(series.skew())
    # pandas reports excess kurtosis; the estimator wants the non-excess value.
    kurtosis = float(series.kurt()) + 3.0
    if not math.isfinite(skew) or not math.isfinite(kurtosis):
        result["reason"] = "return distribution moments are undefined"
        return result
    result["skew"] = skew
    result["kurtosis"] = kurtosis

    variance_term = 1.0 - skew * observed + (kurtosis - 1.0) / 4.0 * observed**2
    if variance_term <= 0.0 or not math.isfinite(variance_term):
        result["reason"] = "Sharpe ratio variance estimate is non-positive"
        return result

    z_score = (observed - expected_max) * math.sqrt(observations - 1) / math.sqrt(variance_term)
    if not math.isfinite(z_score):
        result["reason"] = "deflated statistic is undefined"
        return result

    dsr = float(_NORMAL.cdf(z_score))
    result["dsr"] = dsr
    result["significant"] = dsr >= 0.95
    return result


def rank_correlation(in_sample: list[float], out_of_sample: list[float]) -> float | None:
    """Spearman rank correlation between in-sample and out-of-sample scores.

    This is the question "does ranking candidates on past data tell you
    anything about their future ranking?".  At or below zero, the search has no
    predictive content whatsoever and any winner is a coin flip.
    """
    if len(in_sample) != len(out_of_sample) or len(in_sample) < 3:
        return None
    frame = pd.DataFrame({"is": in_sample, "oos": out_of_sample}, dtype=float)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3 or frame["is"].nunique() < 2 or frame["oos"].nunique() < 2:
        return None
    # Spearman is Pearson on ranks; computing it that way keeps this dependency
    # free (pandas delegates method="spearman" to scipy, which is not a dep).
    ranks = frame.rank(method="average")
    correlation = float(ranks["is"].corr(ranks["oos"]))
    return correlation if math.isfinite(correlation) else None


def label_regimes(df: pd.DataFrame, window: int = 168) -> pd.DataFrame:
    """Label every bar with a funding and a volatility regime.

    Both labels use only trailing information (rolling, then shifted by one
    bar), so a trade can be attributed to the regime that was observable at the
    moment it was opened rather than to one defined with hindsight.

    ``fundingRegime`` is the sign of the trailing median funding rate;
    ``volRegime`` compares trailing realised volatility to its own median over
    the sample, which makes it relative to the period under test rather than to
    an absolute threshold that would not travel across assets.
    """
    labelled = pd.DataFrame(index=df.index)

    if "fundingRate" in df.columns:
        trailing_funding = (
            df["fundingRate"].astype(float).rolling(window, min_periods=max(2, window // 4)).median()
        ).shift(1)
    else:
        trailing_funding = pd.Series(np.nan, index=df.index, dtype=float)
    labelled["fundingRegime"] = np.where(
        trailing_funding.isna(),
        "unknown",
        np.where(trailing_funding > 0, "funding_positive", "funding_negative"),
    )

    returns = df["close"].astype(float).pct_change()
    trailing_vol = returns.rolling(window, min_periods=max(2, window // 4)).std(ddof=1).shift(1)
    median_vol = float(trailing_vol.median()) if trailing_vol.notna().any() else float("nan")
    if math.isfinite(median_vol):
        labelled["volRegime"] = np.where(
            trailing_vol.isna(),
            "unknown",
            np.where(trailing_vol > median_vol, "vol_high", "vol_low"),
        )
    else:
        labelled["volRegime"] = "unknown"

    labelled["regime"] = labelled["fundingRegime"] + " / " + labelled["volRegime"]
    return labelled


def summarise_trades_by_regime(
    trades: list[dict[str, Any]],
    regimes: pd.DataFrame,
    min_trades: int = 5,
) -> list[dict[str, Any]]:
    """Aggregate net trade PnL by the regime in force at each trade's entry bar.

    Buckets holding fewer than ``min_trades`` trades are reported with
    ``sufficient=False`` rather than dropped: a thin bucket is information, and
    silently hiding it invites reading a two-trade bucket as a finding.
    """
    if not trades or regimes.empty:
        return []

    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        entry_time = trade.get("entryTime")
        if not entry_time:
            continue
        timestamp = pd.to_datetime(entry_time, utc=True)
        position = int(regimes.index.searchsorted(timestamp, side="right") - 1)
        if position < 0 or position >= len(regimes):
            continue
        label = str(regimes.iloc[position]["regime"])
        bucket = buckets.setdefault(
            label,
            {
                "regime": label,
                "fundingRegime": str(regimes.iloc[position]["fundingRegime"]),
                "volRegime": str(regimes.iloc[position]["volRegime"]),
                "trades": 0,
                "wins": 0,
                "netPnl": 0.0,
                "returns": [],
            },
        )
        net_pnl = float(trade.get("netPnl", 0.0))
        bucket["trades"] += 1
        bucket["wins"] += 1 if net_pnl > 0 else 0
        bucket["netPnl"] += net_pnl
        bucket["returns"].append(float(trade.get("returnPct", 0.0)))

    summary = []
    for bucket in buckets.values():
        returns = bucket.pop("returns")
        count = int(bucket["trades"])
        bucket["netPnl"] = round(float(bucket["netPnl"]), 2)
        bucket["winRatePct"] = round(bucket["wins"] / count * 100, 2) if count else 0.0
        bucket["avgReturnPct"] = round(float(np.mean(returns)), 4) if returns else 0.0
        bucket["sufficient"] = count >= min_trades
        summary.append(bucket)

    summary.sort(key=lambda item: item["netPnl"], reverse=True)
    return summary
