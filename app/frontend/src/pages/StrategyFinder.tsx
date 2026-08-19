import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Loader2, Save, Search, X } from 'lucide-react';
import { Card } from '../components/Card';
import { useWallet } from '../context/useWallet';
import {
  createStrategy,
  fetchStrategySearch,
  fetchUserFees,
  startStrategySearch,
} from '../services/api';
import type {
  BacktestInterval,
  StrategySearchCandidate,
  StrategySearchInput,
  StrategySearchJob,
  StrategySearchResult,
} from '../types';

const INTERVALS: { label: string; value: BacktestInterval }[] = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
];

const TEMPLATES = [
  'momentum_breakout',
  'mean_reversion',
  'funding_rate_arb',
  'hype_delta_neutral',
  'trend_following',
  'scalp_momentum',
  'news_event',
  'basis_arbitrage',
  'grid_trading',
  'dual_thrust',
  'turtle_breakout',
  'ema_bands_trend_catch',
  'atr_rsi_combo',
  'time_series_momentum',
  'overnight_seasonality_btc',
  'custom',
];

const TEMPLATE_LABELS: Record<string, string> = {
  momentum_breakout: 'Momentum Breakout',
  mean_reversion: 'Mean Reversion',
  funding_rate_arb: 'Funding Rate Arb',
  hype_delta_neutral: 'HYPE Delta Neutral',
  trend_following: 'Trend Following',
  scalp_momentum: 'Scalp Momentum',
  news_event: 'News Event',
  basis_arbitrage: 'Basis Arbitrage',
  grid_trading: 'Grid Trading',
  dual_thrust: 'Dual Thrust',
  turtle_breakout: 'Turtle Breakout',
  ema_bands_trend_catch: 'EMA Bands Trend Catch',
  atr_rsi_combo: 'ATR + RSI Combo',
  time_series_momentum: 'Time-Series Momentum',
  overnight_seasonality_btc: 'Overnight Seasonality BTC',
  custom: 'Custom (fallback signal logic)',
};

const DEFAULT_FEE = { maker: 0.00015, taker: 0.00045 };

function dateDaysAgo(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function formatPct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatSharpe(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(4);
}

function formatCurrency(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  const amount = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${value < 0 ? '-' : value > 0 ? '+' : ''}$${amount}`;
}

function formatDate(value: string) {
  return value.replace('T', ' ').replace(/\+00:00$/, ' UTC').slice(0, 16);
}

function formatOverrides(overrides: Record<string, number>) {
  const labels: Record<string, string> = {
    confidenceFloor: 'conf',
    minHoldBars: 'hold',
    cooldownBars: 'cool',
    stopLossPct: 'SL',
    takeProfitPct: 'TP',
    trailingStopPct: 'trail',
  };
  const protectiveKeys = new Set(['stopLossPct', 'takeProfitPct', 'trailingStopPct']);
  const parts = Object.entries(overrides)
    .filter(([key, value]) => !protectiveKeys.has(key) || value !== 0)
    .map(([key, value]) => {
      const display = key.endsWith('Pct') ? `${(value * 100).toFixed(1)}%` : value;
      return `${labels[key] || key} ${display}`;
    });
  if (!Object.entries(overrides).some(([key, value]) => protectiveKeys.has(key) && value !== 0)) {
    parts.push('no stops');
  }
  return parts.join(' · ');
}

function errorText(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error);
  const body = raw.replace(/^\d+:\s*/, '');
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    return parsed.detail || body;
  } catch {
    return body;
  }
}

type CandidateGroup = {
  key: string;
  candidate: StrategySearchCandidate;
  candidates: StrategySearchCandidate[];
};

type RegimeGroup = {
  key: string;
  breakdown: StrategySearchResult['regimeBreakdown'][number];
  candidateIds: string[];
};

function Field({
  label,
  children,
  className = '',
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">{label}</span>
      {children}
    </label>
  );
}

function inputClass() {
  return 'w-full rounded-lg border border-gray-800 bg-[#0b0d12] px-3 py-2 text-sm text-gray-100 outline-none focus:border-violet-500';
}

function Verdict({
  title,
  children,
  tone = 'violet',
}: {
  title: string;
  children: React.ReactNode;
  tone?: 'violet' | 'emerald' | 'amber' | 'rose';
}) {
  const tones = {
    violet: 'border-violet-500/20 bg-violet-500/5',
    emerald: 'border-emerald-500/20 bg-emerald-500/5',
    amber: 'border-amber-500/20 bg-amber-500/5',
    rose: 'border-rose-500/20 bg-rose-500/5',
  };
  return (
    <div className={`rounded-xl border p-4 ${tones[tone]}`}>
      <div className="text-xs font-semibold uppercase tracking-wider text-gray-400">{title}</div>
      <div className="mt-2 text-sm leading-6 text-gray-200">{children}</div>
    </div>
  );
}

export function StrategyFinder() {
  const { selectedWallet } = useWallet();
  const [symbol, setSymbol] = useState('BTC');
  const [interval, setInterval] = useState<BacktestInterval>('1h');
  const [startAt, setStartAt] = useState(dateDaysAgo(60));
  const [endAt, setEndAt] = useState(new Date().toISOString().slice(0, 10));
  const [templates, setTemplates] = useState<string[]>(TEMPLATES);
  const [folds, setFolds] = useState(4);
  const [gridPreset, setGridPreset] = useState<'standard' | 'coarse'>('coarse');
  const [minTradesIS, setMinTradesIS] = useState(5);
  const [initialBalance, setInitialBalance] = useState(10_000);
  const [makerFee, setMakerFee] = useState(DEFAULT_FEE.maker);
  const [takerFee, setTakerFee] = useState(DEFAULT_FEE.taker);
  const [slippagePct, setSlippagePct] = useState(0.00005);
  const [orderType, setOrderType] = useState<'maker' | 'taker'>('taker');
  const [feeSource, setFeeSource] = useState<'generic_default' | 'wallet' | 'manual'>('generic_default');
  const [job, setJob] = useState<StrategySearchJob | null>(null);
  const [result, setResult] = useState<StrategySearchResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [savedCandidate, setSavedCandidate] = useState('');
  const [savingCandidate, setSavingCandidate] = useState('');
  const [showAllCandidates, setShowAllCandidates] = useState(false);

  useEffect(() => {
    let active = true;
    if (!selectedWallet) {
      setMakerFee(DEFAULT_FEE.maker);
      setTakerFee(DEFAULT_FEE.taker);
      setFeeSource('generic_default');
      return undefined;
    }
    fetchUserFees(selectedWallet.address)
      .then((fees) => {
        if (!active) return;
        setMakerFee(fees.makerFee);
        setTakerFee(fees.takerFee);
        setFeeSource('wallet');
      })
      .catch(() => {
        if (!active) return;
        setMakerFee(DEFAULT_FEE.maker);
        setTakerFee(DEFAULT_FEE.taker);
        setFeeSource('generic_default');
      });
    return () => {
      active = false;
    };
  }, [selectedWallet]);

  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'error') return undefined;
    const timer = window.setTimeout(() => {
      fetchStrategySearch(job.id)
        .then((next) => {
          setJob(next);
          if (next.status === 'done') setResult(next.result);
        })
        .catch((pollError) => setError(errorText(pollError)));
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [job]);

  const estimatedSimulations = useMemo(() => {
    const perTemplate = gridPreset === 'coarse' ? 8 : 120;
    return templates.length * perTemplate * (2 * folds + 1);
  }, [folds, gridPreset, templates.length]);

  function toggleTemplate(template: string) {
    setTemplates((current) =>
      current.includes(template) ? current.filter((item) => item !== template) : [...current, template],
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!templates.length) {
      setError('Select at least one template.');
      return;
    }
    setError('');
    setResult(null);
    setSavedCandidate('');
    setShowAllCandidates(false);
    setSubmitting(true);
    const payload: StrategySearchInput = {
      symbol: symbol.trim().toUpperCase(),
      interval,
      startAt,
      endAt,
      templates,
      folds,
      minTradesIS,
      gridPreset,
      initialBalance,
      makerFee,
      takerFee,
      slippagePct,
      orderType,
      feeSource,
      slippageSource: 'default',
    };
    try {
      const next = await startStrategySearch(payload);
      setJob(next);
      if (next.status === 'done') setResult(next.result);
    } catch (submitError) {
      setError(errorText(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveCandidate(candidate: StrategySearchCandidate) {
    if (!result) return;
    setSavingCandidate(candidate.candidateId);
    setError('');
    try {
      await createStrategy({
        name: `${candidate.template} search ${result.symbol} ${result.startAt}–${result.endAt}`,
        description: `Saved from Strategy Finder (${result.gridPreset}, ${result.folds} folds). Candidate ${candidate.candidateId}; historical search result, not a forecast.`,
        template: candidate.template,
        markets: [result.symbol],
        agents: ['Market', 'Funding', 'OrderBook'],
        riskConfig: candidate.riskConfig,
      });
      setSavedCandidate(candidate.candidateId);
    } catch (saveError) {
      setError(errorText(saveError));
    } finally {
      setSavingCandidate('');
    }
  }

  const running = job?.status === 'queued' || job?.status === 'running';
  const selectedByFold = new Map((result?.selection.selectedFolds || []).map((fold) => [fold.fold, fold]));
  const candidateGroups = useMemo<CandidateGroup[]>(() => {
    if (!result) return [];
    const groups = new Map<string, CandidateGroup>();
    result.candidates.forEach((candidate) => {
      const { candidateId: _candidateId, overrides: _overrides, riskConfig: _riskConfig, ...metrics } = candidate;
      const key = JSON.stringify(metrics);
      const existing = groups.get(key);
      if (existing) {
        existing.candidates.push(candidate);
      } else {
        groups.set(key, { key, candidate, candidates: [candidate] });
      }
    });
    return Array.from(groups.values());
  }, [result]);
  const regimeGroups = useMemo<RegimeGroup[]>(() => {
    if (!result) return [];
    const groups = new Map<string, RegimeGroup>();
    result.regimeBreakdown.forEach((breakdown) => {
      const key = JSON.stringify({ template: breakdown.template, regimes: breakdown.regimes });
      const existing = groups.get(key);
      if (existing) {
        existing.candidateIds.push(breakdown.candidateId);
      } else {
        groups.set(key, { key, breakdown, candidateIds: [breakdown.candidateId] });
      }
    });
    return Array.from(groups.values());
  }, [result]);
  const winnerGroup = result
    ? candidateGroups.find((group) => group.candidates.some((candidate) => candidate.candidateId === result.fullRangeWinner.candidateId))
    : undefined;
  const visibleCandidateGroups = showAllCandidates
    ? candidateGroups
    : candidateGroups.slice(0, 25).concat(winnerGroup && !candidateGroups.slice(0, 25).includes(winnerGroup) ? [winnerGroup] : []);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Strategy Finder</h1>
        <p className="mt-1 text-sm text-gray-400">
          Compare parameterised historical strategies with anchored walk-forward evaluation.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1 whitespace-pre-wrap">{error}</span>
          <button type="button" onClick={() => setError('')} aria-label="Dismiss error">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <Card title="Search configuration">
        <form onSubmit={submit} className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Symbol">
              <input className={inputClass()} value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
            </Field>
            <Field label="Interval">
              <select className={inputClass()} value={interval} onChange={(event) => setInterval(event.target.value as BacktestInterval)}>
                {INTERVALS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </Field>
            <Field label="Start date">
              <input type="date" className={inputClass()} value={startAt} onChange={(event) => setStartAt(event.target.value)} />
            </Field>
            <Field label="End date">
              <input type="date" className={inputClass()} value={endAt} onChange={(event) => setEndAt(event.target.value)} />
            </Field>
            <Field label="Folds">
              <input type="number" min={2} max={6} className={inputClass()} value={folds} onChange={(event) => setFolds(Number(event.target.value))} />
            </Field>
            <Field label="Grid preset">
              <select className={inputClass()} value={gridPreset} onChange={(event) => setGridPreset(event.target.value as 'standard' | 'coarse')}>
                <option value="coarse">Coarse (recommended)</option>
                <option value="standard">Standard</option>
              </select>
            </Field>
            <Field label="Min in-sample trades">
              <input type="number" min={0} className={inputClass()} value={minTradesIS} onChange={(event) => setMinTradesIS(Number(event.target.value))} />
            </Field>
            <Field label="Initial balance">
              <input type="number" min={0} step="100" className={inputClass()} value={initialBalance} onChange={(event) => setInitialBalance(Number(event.target.value))} />
            </Field>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-gray-500">Templates</span>
              <div className="flex gap-2 text-xs">
                <button type="button" className="text-violet-400 hover:text-violet-300" onClick={() => setTemplates(TEMPLATES)}>All</button>
                <button type="button" className="text-gray-400 hover:text-gray-200" onClick={() => setTemplates([])}>Clear</button>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {TEMPLATES.map((template) => {
                const checked = templates.includes(template);
                return (
                  <label key={template} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${checked ? 'border-violet-500/40 bg-violet-500/10 text-violet-200' : 'border-gray-800 text-gray-500 hover:border-gray-700'}`}>
                    <input type="checkbox" className="accent-violet-500" checked={checked} onChange={() => toggleTemplate(template)} />
                    {TEMPLATE_LABELS[template]}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-gray-800 pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={`Maker fee${feeSource === 'wallet' ? ' · wallet tier' : ''}`}>
              <input type="number" min={0} step="0.00001" className={inputClass()} value={makerFee} onChange={(event) => { setMakerFee(Number(event.target.value)); setFeeSource('manual'); }} />
            </Field>
            <Field label={`Taker fee${feeSource === 'wallet' ? ' · wallet tier' : ''}`}>
              <input type="number" min={0} step="0.00001" className={inputClass()} value={takerFee} onChange={(event) => { setTakerFee(Number(event.target.value)); setFeeSource('manual'); }} />
            </Field>
            <Field label="Slippage">
              <input type="number" min={0} step="0.00001" className={inputClass()} value={slippagePct} onChange={(event) => setSlippagePct(Number(event.target.value))} />
            </Field>
            <Field label="Order type">
              <select className={inputClass()} value={orderType} onChange={(event) => setOrderType(event.target.value as 'maker' | 'taker')}>
                <option value="taker">Taker</option>
                <option value="maker">Maker</option>
              </select>
            </Field>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-gray-500">
              Estimated workload: {templates.length} templates · {estimatedSimulations.toLocaleString()} simulations. Coarse is the safer default for long ranges.
            </p>
            <button type="submit" disabled={submitting || running} className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50">
              {submitting || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {running ? 'Search running…' : 'Run strategy search'}
            </button>
          </div>
        </form>
      </Card>

      {job && (
        <Card title={job.status === 'done' ? 'Search complete' : 'Search progress'}>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="capitalize text-gray-300">{job.status}</span>
              <span className="text-gray-400">{job.progress.completed.toLocaleString()} / {job.progress.total.toLocaleString()} simulations</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-800">
              <div className="h-full rounded-full bg-violet-500 transition-all" style={{ width: `${job.progress.total ? Math.min(100, job.progress.completed / job.progress.total * 100) : 0}%` }} />
            </div>
            <p className="text-xs text-gray-500">
              {job.candidateCount.toLocaleString()} candidates · {job.simulationCount.toLocaleString()} simulations
              {running && '. Historical searches can take several minutes; this page will keep polling until the job finishes.'}
            </p>
            {job.error && <p className="whitespace-pre-wrap text-sm text-rose-300">{job.error}</p>}
          </div>
        </Card>
      )}

      {result && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Verdict title="Did optimising help at all?" tone={result.selection.returnPct >= result.selection.buyAndHoldReturnPct ? 'emerald' : 'rose'}>
              <strong>{result.selection.returnPct >= result.selection.buyAndHoldReturnPct ? 'Yes, in this history.' : 'No — buy-and-hold did better.'}</strong>{' '}
              Selection compounded to <strong>{formatPct(result.selection.returnPct)}</strong> versus <strong>{formatPct(result.selection.buyAndHoldReturnPct)}</strong> over the same test windows.
            </Verdict>
            <Verdict title="Is the winner distinguishable from noise?" tone={result.deflatedSharpeRatio?.significant ? 'emerald' : 'amber'}>
              {result.deflatedSharpeRatio ? (
                <>DSR <strong>{result.deflatedSharpeRatio.dsr == null ? 'unavailable' : result.deflatedSharpeRatio.dsr.toFixed(3)}</strong> ({result.deflatedSharpeRatio.significant ? 'significant' : 'not significant'}). Observed Sharpe {formatSharpe(result.deflatedSharpeRatio.observedSharpe)} versus expected maximum {formatSharpe(result.deflatedSharpeRatio.expectedMaxSharpe)} across {result.deflatedSharpeRatio.trials.toLocaleString()} trials.</>
              ) : <>DSR unavailable: <strong>{'No full-range DSR was returned.'}</strong></>}
              {result.deflatedSharpeRatio?.reason && <> Reason: <strong>{result.deflatedSharpeRatio.reason}</strong></>}
            </Verdict>
            <Verdict title="Does in-sample ranking predict out-of-sample ranking?" tone={(result.rankCorrelation ?? 0) > 0 ? 'violet' : 'amber'}>
              Rank correlation is <strong>{result.rankCorrelation == null ? 'unavailable' : result.rankCorrelation.toFixed(3)}</strong>.{' '}
              {result.rankCorrelation == null || result.rankCorrelation <= 0 ? 'At or below zero means the in-sample ranking carries no predictive content; the table below is a historical record, not a forecast.' : 'Positive correlation is limited historical evidence, not a prediction of future winners.'}
            </Verdict>
          </div>

          {result.selection.foldsSkipped > 0 && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              Selection covers {result.selection.foldsConsidered} of {result.folds} test folds. Skipped folds: {result.selection.skippedFolds.map((fold) => `${fold.fold} (${fold.reason})`).join(', ')}.
            </div>
          )}

          <Card title={`Candidates · ranked by median out-of-sample per-bar Sharpe`}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1100px] text-left text-xs">
                <thead className="border-b border-gray-800 text-gray-500">
                  <tr>{['Candidate', 'Overrides', 'Median / mean OOS return', 'Median OOS Sharpe', 'Annualised', 'OOS trades', 'Folds', 'Overfit gap', 'Full return', ''].map((heading) => <th key={heading} className="px-3 py-2 font-medium">{heading}</th>)}</tr>
                </thead>
                <tbody>
                  {visibleCandidateGroups.map((group) => {
                    const { candidate } = group;
                    const isWinner = group.candidates.some((item) => item.candidateId === result.fullRangeWinner.candidateId);
                    return (
                      <tr key={group.key} className={`border-b border-gray-800/70 ${isWinner ? 'bg-amber-500/10 ring-1 ring-inset ring-amber-400/50' : 'hover:bg-gray-800/30'}`}>
                        <td className="px-3 py-3">
                          <div className="font-medium text-gray-200">{TEMPLATE_LABELS[candidate.template] || candidate.template}</div>
                          <div className="text-[10px] text-gray-500">{candidate.candidateId}{isWinner ? ' · full-range winner' : ''}</div>
                        </td>
                        <td className="max-w-[250px] px-3 py-3 text-gray-400">
                          {formatOverrides(candidate.overrides)}
                          {group.candidates.length > 1 && (
                            <details className="mt-1 text-[10px] text-gray-500">
                              <summary className="cursor-pointer text-violet-300">{group.candidates.length} identical parameter sets</summary>
                              <ul className="mt-1 space-y-1 pl-3">
                                {group.candidates.map((item) => <li key={item.candidateId}>{item.candidateId}: {formatOverrides(item.overrides)}</li>)}
                              </ul>
                            </details>
                          )}
                        </td>
                        <td className="px-3 py-3 text-gray-300">{formatPct(candidate.medianOutOfSampleReturnPct)} / {formatPct(candidate.meanOutOfSampleReturnPct)}</td>
                        <td className="px-3 py-3 text-gray-300">{formatSharpe(candidate.medianOutOfSampleSharpePerBar)}</td>
                        <td className="px-3 py-3 text-gray-300">{formatSharpe(candidate.medianOutOfSampleSharpeAnnualised)}</td>
                        <td className="px-3 py-3 text-gray-300">{candidate.totalOutOfSampleTrades}</td>
                        <td className="px-3 py-3 text-gray-300">{candidate.foldsWithTrades}/{result.folds}</td>
                        <td className={`px-3 py-3 ${candidate.overfitGap != null && candidate.overfitGap > 0 ? 'text-amber-300' : 'text-gray-300'}`}>{formatSharpe(candidate.overfitGap)}</td>
                        <td className="px-3 py-3 text-gray-300">{formatPct(candidate.fullRange.returnPct)}</td>
                        <td className="px-3 py-3">
                          <button type="button" onClick={() => saveCandidate(candidate)} disabled={savingCandidate !== ''} className="inline-flex items-center gap-1 rounded-md bg-gray-800 px-2 py-1.5 text-gray-300 hover:bg-gray-700 disabled:opacity-50" title="Save candidate as a strategy">
                            {savingCandidate === candidate.candidateId ? <Loader2 className="h-3 w-3 animate-spin" /> : savedCandidate === candidate.candidateId ? <Check className="h-3 w-3 text-emerald-400" /> : <Save className="h-3 w-3" />}
                            {savedCandidate === candidate.candidateId ? 'Saved' : 'Save'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {candidateGroups.length > 25 && (
              <button type="button" onClick={() => setShowAllCandidates((current) => !current)} className="mt-3 text-xs text-violet-300 hover:text-violet-200">
                {showAllCandidates ? 'Show top 25 collapsed rows' : `Show all ${candidateGroups.length} collapsed rows`}
              </button>
            )}
          </Card>

          <Card title="Selected walk-forward folds">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[950px] text-left text-xs">
                <thead className="border-b border-gray-800 text-gray-500">
                  <tr>{['Fold', 'Train window', 'Test window', 'Selected candidate', 'IS Sharpe', 'OOS return', 'OOS Sharpe'].map((heading) => <th key={heading} className="px-3 py-2 font-medium">{heading}</th>)}</tr>
                </thead>
                <tbody>
                  {Array.from({ length: result.folds }, (_, index) => index + 1).map((foldNumber) => {
                    const fold = selectedByFold.get(foldNumber);
                    const skipped = result.selection.skippedFolds.find((item) => item.fold === foldNumber);
                    return (
                      <tr key={foldNumber} className="border-b border-gray-800/70">
                        <td className="px-3 py-3 text-gray-300">{foldNumber}</td>
                        <td className="px-3 py-3 text-gray-400">{fold ? `${formatDate(fold.trainStart)} → ${formatDate(fold.trainEnd)}` : skipped ? `${formatDate(skipped.trainStart)} → ${formatDate(skipped.trainEnd)}` : '—'}</td>
                        <td className="px-3 py-3 text-gray-400">{fold ? `${formatDate(fold.testStart)} → ${formatDate(fold.testEnd)}` : skipped ? `${formatDate(skipped.testStart)} → ${formatDate(skipped.testEnd)}` : '—'}</td>
                        {fold ? (
                          <>
                            <td className="px-3 py-3 text-gray-300">{TEMPLATE_LABELS[fold.template] || fold.template}<div className="text-[10px] text-gray-500">{fold.candidateId}</div></td>
                            <td className="px-3 py-3 text-gray-300">{formatSharpe(fold.inSample.perBarSharpe)}</td>
                            <td className="px-3 py-3 text-gray-300">{formatPct(fold.outOfSample.returnPct)}</td>
                            <td className="px-3 py-3 text-gray-300">{formatSharpe(fold.outOfSample.perBarSharpe)}</td>
                          </>
                        ) : (
                          <td colSpan={4} className="px-3 py-3 text-amber-300">Skipped: {skipped?.reason || 'no eligible candidate'}</td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Regime breakdown">
            <p className="mb-4 text-xs text-gray-500">Reported for the top three out-of-sample candidates plus the full-range winner. Thin buckets are shown, not promoted to findings.</p>
            <div className="space-y-5">
              {regimeGroups.map((group) => {
                const { breakdown } = group;
                const isWinner = group.candidateIds.includes(result.fullRangeWinner.candidateId);
                return (
                <div key={group.key}>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-sm font-medium text-gray-200">
                    {TEMPLATE_LABELS[breakdown.template] || breakdown.template}
                    <span className="text-xs text-gray-500">{breakdown.candidateId}</span>
                    {isWinner && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">full-range winner</span>}
                    {group.candidateIds.length > 1 && (
                      <details className="text-[10px] font-normal text-gray-500">
                        <summary className="cursor-pointer text-violet-300">{group.candidateIds.length} identical parameter sets</summary>
                        <div className="mt-1 rounded border border-gray-800 bg-gray-900/50 p-2">
                          {group.candidateIds.join(', ')}
                        </div>
                      </details>
                    )}
                  </div>
                  {breakdown.regimes.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[720px] text-left text-xs">
                        <thead className="border-b border-gray-800 text-gray-500">
                          <tr>{['Regime', 'Funding', 'Volatility', 'Trades', 'Win rate', 'Net PnL', 'Avg return', 'Sample'].map((heading) => <th key={heading} className="px-3 py-2 font-medium">{heading}</th>)}</tr>
                        </thead>
                        <tbody>
                          {breakdown.regimes.map((regime) => (
                            <tr key={`${breakdown.candidateId}-${regime.regime}`} className={`border-b border-gray-800/70 ${regime.sufficient ? '' : 'bg-amber-500/5 text-amber-200'}`}>
                              <td className="px-3 py-2 text-gray-300">{regime.regime}</td>
                              <td className="px-3 py-2 text-gray-400">{regime.fundingRegime}</td>
                              <td className="px-3 py-2 text-gray-400">{regime.volRegime}</td>
                              <td className="px-3 py-2">{regime.trades}</td>
                              <td className="px-3 py-2">{formatPct(regime.winRatePct)}</td>
                              <td className="px-3 py-2">{formatCurrency(regime.netPnl)}</td>
                              <td className="px-3 py-2">{formatPct(regime.avgReturnPct)}</td>
                              <td className="px-3 py-2">{regime.sufficient ? 'sufficient' : 'thin sample'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : <p className="text-xs text-gray-500">No trades in the reported regimes.</p>}
                </div>
                );
              })}
            </div>
          </Card>

          <p className="pb-4 text-center text-xs text-gray-500">This search reports what worked in the past. It does not predict future performance.</p>
        </div>
      )}
    </div>
  );
}
