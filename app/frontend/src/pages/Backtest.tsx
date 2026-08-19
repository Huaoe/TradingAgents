import { useEffect, useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Brush,
} from 'recharts';
import { Play, Loader2, TrendingUp, TrendingDown, Activity, Percent, DollarSign, BarChart3, Calendar, ZoomIn, ZoomOut, RotateCcw, AlertTriangle } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { Card } from '../components/Card';
import { fetchStrategies, runBacktest, updateStrategy } from '../services/api';
import type { Strategy, BacktestResult, BacktestInterval } from '../types';

const intervals: { label: string; value: BacktestInterval }[] = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
];

function toInputDate(iso: string) {
  return iso.slice(0, 10);
}

function formatPct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatUSD(value: number) {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatNumber(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const STAT_HINTS: Record<string, string> = {
  'Total Return': 'Total percentage gain or loss over the backtest period.',
  'Benchmark Return': 'Buy-and-hold return for the same symbol and period.',
  'Sharpe Ratio': 'Risk-adjusted return; higher is better.',
  'Max Drawdown': 'Largest peak-to-trough decline in equity.',
  'Win Rate': 'Percentage of trades that closed with a positive net PnL.',
  'Profit Factor': 'Gross profit divided by gross loss.',
  '# Trades': 'Total number of round-trip trades executed.',
  'Final Balance': 'Account value at the end of the backtest.',
  'Avg Win': 'Average return percent of winning trades.',
  'Avg Loss': 'Average return percent of losing trades.',
  'Confidence Floor': 'Minimum confidence score needed to enter a long or short position.',
  'Final Signal': 'The strategy\'s most recent bar signal.',
  'Signal Mix': 'Number of long, short, and flat bars over the period.',
  Leverage: 'Effective leverage used per position.',
  Allocation: 'Percentage of the portfolio allocated to each trade.',
};

const TRADE_HINTS: Record<string, string> = {
  Entry: 'Time the position was opened.',
  Exit: 'Time the position was closed.',
  Side: 'LONG or SHORT direction of the trade.',
  'Entry $': 'Entry price of the trade.',
  'Exit $': 'Exit price of the trade.',
  Size: 'Position size in coins.',
  'Net PnL': 'Net profit or loss after fees and funding.',
  Return: 'Net return percent on the trade, after fees and funding.',
  Confidence: 'Signal confidence score at entry (0-100).',
};

function formatSide(signal: number) {
  if (signal > 0) return 'LONG';
  if (signal < 0) return 'SHORT';
  return 'FLAT';
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function useChartZoom<T>(data: T[], minItems = 20) {
  const [startIndex, setStartIndex] = useState(0);
  const [endIndex, setEndIndex] = useState(0);

  useEffect(() => {
    setStartIndex(0);
    setEndIndex(Math.max(0, data.length - 1));
  }, [data.length]);

  function setRange(range: { startIndex?: number; endIndex?: number }) {
    if (!data.length) return;
    let start = typeof range.startIndex === 'number' ? Math.round(range.startIndex) : startIndex;
    let end = typeof range.endIndex === 'number' ? Math.round(range.endIndex) : endIndex;
    if (end - start + 1 < minItems) {
      const center = Math.round((start + end) / 2);
      start = Math.max(0, center - Math.floor((minItems - 1) / 2));
      end = Math.min(data.length - 1, start + minItems - 1);
      if (end - start + 1 < minItems) {
        start = Math.max(0, end - minItems + 1);
      }
    }
    start = clamp(start, 0, data.length - 1);
    end = clamp(end, start, data.length - 1);
    setStartIndex(start);
    setEndIndex(end);
  }

  function zoomIn() {
    if (!data.length) return;
    const current = endIndex - startIndex + 1;
    const newWidth = Math.max(Math.round(current * 0.8), minItems);
    const center = Math.round((startIndex + endIndex) / 2);
    let newStart = center - Math.floor(newWidth / 2);
    let newEnd = newStart + newWidth - 1;
    if (newStart < 0) {
      newEnd -= newStart;
      newStart = 0;
    }
    if (newEnd >= data.length) {
      newStart -= newEnd - (data.length - 1);
      newEnd = data.length - 1;
    }
    setStartIndex(Math.max(0, newStart));
    setEndIndex(Math.min(data.length - 1, newEnd));
  }

  function zoomOut() {
    if (!data.length) return;
    const current = endIndex - startIndex + 1;
    const newWidth = Math.min(Math.round(current / 0.8), data.length);
    const center = Math.round((startIndex + endIndex) / 2);
    let newStart = center - Math.floor(newWidth / 2);
    let newEnd = newStart + newWidth - 1;
    if (newStart < 0) {
      newEnd -= newStart;
      newStart = 0;
    }
    if (newEnd >= data.length) {
      newStart -= newEnd - (data.length - 1);
      newEnd = data.length - 1;
    }
    setStartIndex(Math.max(0, newStart));
    setEndIndex(Math.min(data.length - 1, newEnd));
  }

  function reset() {
    setStartIndex(0);
    setEndIndex(Math.max(0, data.length - 1));
  }

  const visibleData = useMemo(() => {
    if (!data.length) return [];
    const from = startIndex;
    const to = Math.max(from + 1, endIndex + 1);
    return data.slice(from, to);
  }, [data, startIndex, endIndex]);

  function onBrushChange(range: { startIndex?: number; endIndex?: number }) {
    if (!data.length) return;
    const start = typeof range.startIndex === 'number' ? range.startIndex : 0;
    const end = typeof range.endIndex === 'number' ? range.endIndex : visibleData.length - 1;
    setRange({ startIndex: start + startIndex, endIndex: end + startIndex });
  }

  return { visibleData, zoomIn, zoomOut, reset, startIndex, endIndex, setRange, onBrushChange };
}

function ZoomControls({ zoomIn, zoomOut, reset }: { zoomIn: () => void; zoomOut: () => void; reset: () => void }) {
  return (
    <div className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={zoomOut}
        title="Zoom out"
        className="p-1 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
      >
        <ZoomOut className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={reset}
        title="Reset view"
        className="p-1 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
      >
        <RotateCcw className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={zoomIn}
        title="Zoom in"
        className="p-1 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
      >
        <ZoomIn className="w-4 h-4" />
      </button>
    </div>
  );
}

export function Backtest() {
  const [searchParams] = useSearchParams();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState(searchParams.get('strategy') || '');
  const [symbol, setSymbol] = useState(searchParams.get('symbol')?.toUpperCase() || 'BTC');
  const [interval, setInterval] = useState<BacktestInterval>('1h');
  const end = useMemo(() => new Date().toISOString(), []);
  const start = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString();
  }, []);
  const [startAt, setStartAt] = useState(toInputDate(start));
  const [endAt, setEndAt] = useState(toInputDate(end));
  const [initialBalance, setInitialBalance] = useState(10000);
  const [makerFee, setMakerFee] = useState(0.0002);
  const [takerFee, setTakerFee] = useState(0.00045);
  const [slippagePct, setSlippagePct] = useState(0.0005);
  const [orderType, setOrderType] = useState<'maker' | 'taker'>('taker');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [activated, setActivated] = useState(false);

  useEffect(() => {
    fetchStrategies().then((list) => {
      setStrategies(list);
      const param = searchParams.get('strategy');
      if (param && list.some((s) => s.id === param)) {
        setStrategyId(param);
      } else if (!param) {
        const saved = list.find((s) => !s.id.startsWith('template-'));
        if (saved) setStrategyId(saved.id);
      }
    }).catch(() => setStrategies([]));
  }, [searchParams]);

  async function handleRun(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    setActivated(false);
    try {
      const res = await runBacktest({
        symbol: symbol.toUpperCase(),
        interval,
        startAt: new Date(startAt).toISOString(),
        endAt: new Date(endAt).toISOString(),
        strategyId: strategyId || undefined,
        initialBalance,
        makerFee,
        takerFee,
        slippagePct,
        orderType,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleActivate() {
    if (!strategyId || !result) return;
    try {
      await updateStrategy(strategyId, { executionMode: 'manual' });
      setActivated(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed');
    }
  }

  const priceChartData = useMemo(() => {
    if (!result) return [];
    const data = result.price.map((p) => ({ ...p, buy: null as number | null, sell: null as number | null }));
    const map = new Map(data.map((d, i) => [d.time, i]));
    for (const t of result.trades) {
      const entryIdx = map.get(t.entryTime);
      const exitIdx = map.get(t.exitTime);
      if (t.side === 'LONG') {
        if (entryIdx != null) data[entryIdx].buy = t.entryPrice;
        if (exitIdx != null) data[exitIdx].sell = t.exitPrice;
      } else {
        if (entryIdx != null) data[entryIdx].sell = t.entryPrice;
        if (exitIdx != null) data[exitIdx].buy = t.exitPrice;
      }
    }
    return data;
  }, [result]);

  const equityZoom = useChartZoom(result?.equity ?? []);
  const drawdownZoom = useChartZoom(result?.drawdown ?? []);
  const priceZoom = useChartZoom(priceChartData);

  const stats = result?.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Backtest Lab</h1>
          <p className="text-sm text-gray-400 mt-1">
            Run a strategy against historical Hyperliquid candles and compare to buy-and-hold.
          </p>
        </div>
      </div>

      <Card>
        <form onSubmit={handleRun} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400">Strategy</label>
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            >
              <option value="">Default (custom rules)</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="BTC"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400">Interval</label>
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as BacktestInterval)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            >
              {intervals.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400">Initial Balance (USD)</label>
            <input
              type="number"
              value={initialBalance}
              onChange={(e) => setInitialBalance(Number(e.target.value))}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> Start Date
            </label>
            <input
              type="date"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> End Date
            </label>
            <input
              type="date"
              value={endAt}
              onChange={(e) => setEndAt(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            />
          </div>

          <div className="lg:col-span-2 flex items-end">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-xs text-violet-400 hover:text-violet-300"
            >
              {showAdvanced ? 'Hide' : 'Show'} advanced parameters
            </button>
          </div>

          {showAdvanced && (
            <>
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-400">Maker Fee</label>
                <input
                  type="number"
                  step="0.00001"
                  value={makerFee}
                  onChange={(e) => setMakerFee(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-400">Taker Fee</label>
                <input
                  type="number"
                  step="0.00001"
                  value={takerFee}
                  onChange={(e) => setTakerFee(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
              <div className="space-y-1 lg:col-span-2">
                <label className="text-xs font-medium text-gray-400">Order Type</label>
                <select
                  value={orderType}
                  onChange={(e) => setOrderType(e.target.value as 'maker' | 'taker')}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                >
                  <option value="taker">Taker (fee + slippage)</option>
                  <option value="maker">Maker (maker fee, no slippage)</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-400">Slippage %</label>
                <input
                  type="number"
                  step="0.0001"
                  value={slippagePct}
                  onChange={(e) => setSlippagePct(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
            </>
          )}

          <div className="lg:col-span-4 flex items-center gap-3">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run Backtest
            </button>
            {result && strategyId && (
              <button
                type="button"
                onClick={handleActivate}
                disabled={activated}
                className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                {activated ? 'Activated' : 'Activate as Paper Strategy'}
              </button>
            )}
          </div>
        </form>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <div className="flex-1">{error}</div>
            <button
              type="button"
              onClick={() => { setError(''); handleRun({ preventDefault: () => {} } as React.FormEvent); }}
              className="text-violet-400 hover:text-violet-300 text-xs font-medium"
            >
              Retry
            </button>
          </div>
        )}

        {loading && !result && (
          <div className="mt-4 space-y-3">
            <div className="h-4 w-32 bg-gray-800 rounded animate-pulse" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-20 bg-gray-800 rounded animate-pulse" />
              ))}
            </div>
          </div>
        )}
      </Card>

      {stats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total Return"
              value={formatPct(stats.totalReturnPct)}
              icon={stats.totalReturnPct >= 0 ? TrendingUp : TrendingDown}
              positive={stats.totalReturnPct >= 0}
            />
            <StatCard
              label="Benchmark Return"
              value={formatPct(stats.benchmarkReturnPct)}
              icon={BarChart3}
              positive={stats.benchmarkReturnPct >= 0}
            />
            <StatCard label="Sharpe Ratio" value={formatNumber(stats.sharpeRatio)} icon={Activity} />
            <StatCard
              label="Max Drawdown"
              value={formatPct(-stats.maxDrawdownPct)}
              icon={TrendingDown}
              positive={false}
            />
            <StatCard label="Win Rate" value={formatPct(stats.winRatePct)} icon={Percent} />
            <StatCard label="Net Profit Factor" value={formatNumber(stats.profitFactor)} icon={BarChart3} />
            <StatCard label="Gross Profit Factor" value={formatNumber(stats.grossProfitFactor)} icon={BarChart3} />
            <StatCard label="# Trades" value={String(stats.totalTrades)} icon={Activity} />
            <StatCard
              label="Final Balance"
              value={formatUSD(stats.finalBalance)}
              icon={DollarSign}
              positive={stats.finalBalance >= stats.initialBalance}
            />
            <StatCard
              label="Avg Win"
              value={formatPct(stats.avgWinPct)}
              icon={TrendingUp}
              positive={stats.avgWinPct >= 0}
            />
            <StatCard
              label="Avg Loss"
              value={formatPct(stats.avgLossPct)}
              icon={TrendingDown}
              positive={false}
            />
            <StatCard label="Confidence Floor" value={String(stats.confidenceFloor)} icon={Percent} />
            <StatCard label="Final Signal" value={formatSide(stats.finalSignal)} icon={Activity} />
            <StatCard
              label="Signal Mix"
              value={`L ${stats.longSignals} · S ${stats.shortSignals} · F ${stats.flatSignals}`}
              icon={BarChart3}
            />
            <StatCard label="Leverage" value={`${stats.leverage}x`} icon={Activity} />
            <StatCard
              label="Allocation"
              value={formatPct(stats.allocation * 100)}
              icon={DollarSign}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card title="Equity Curve" actions={<ZoomControls zoomIn={equityZoom.zoomIn} zoomOut={equityZoom.zoomOut} reset={equityZoom.reset} />}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={equityZoom.visibleData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="time"
                      tickFormatter={(t) => new Date(t).toLocaleDateString()}
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 10 }}
                      minTickGap={30}
                    />
                    <YAxis
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 10 }}
                      tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                      labelFormatter={(label) => new Date(String(label)).toLocaleString()}
                      formatter={(value) => [formatUSD(Number(value)), 'Equity']}
                    />
                    <Line type="monotone" dataKey="equity" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                    <Brush
                      startIndex={0}
                      endIndex={Math.max(0, equityZoom.visibleData.length - 1)}
                      onChange={equityZoom.onBrushChange}
                      height={30}
                      travellerWidth={8}
                      stroke="#8b5cf6"
                      fill="rgba(139, 92, 246, 0.2)"
                      tickFormatter={(t: string) => new Date(t).toLocaleDateString()}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Drawdown" actions={<ZoomControls zoomIn={drawdownZoom.zoomIn} zoomOut={drawdownZoom.zoomOut} reset={drawdownZoom.reset} />}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={drawdownZoom.visibleData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="time"
                      tickFormatter={(t) => new Date(t).toLocaleDateString()}
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 10 }}
                      minTickGap={30}
                    />
                    <YAxis
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 10 }}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                      labelFormatter={(label) => new Date(String(label)).toLocaleString()}
                      formatter={(value) => [`${value}%`, 'Drawdown']}
                    />
                    <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
                    <Brush
                      startIndex={0}
                      endIndex={Math.max(0, drawdownZoom.visibleData.length - 1)}
                      onChange={drawdownZoom.onBrushChange}
                      height={30}
                      travellerWidth={8}
                      stroke="#ef4444"
                      fill="rgba(239, 68, 68, 0.2)"
                      tickFormatter={(t: string) => new Date(t).toLocaleDateString()}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card title="Cost Breakdown">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
              <div>
                <div className="text-xs text-gray-500">Gross PnL</div>
                <div className={`font-semibold ${stats.totalGrossPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatUSD(stats.totalGrossPnl)}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Fees</div>
                <div className="font-semibold text-red-300">{formatUSD(-stats.totalFees)}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Funding</div>
                <div className="font-semibold text-red-300">{formatUSD(-stats.totalFundingCost)}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Net PnL</div>
                <div className={`font-semibold ${stats.totalNetPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatUSD(stats.totalNetPnl)}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Assumptions</div>
                <div className="text-gray-300">
                  {stats.orderType} · fee {(stats.orderType === 'maker' ? stats.makerFee : stats.takerFee) * 10000} bps
                  {stats.orderType === 'taker' ? ` + ${stats.slippagePct * 10000} bps slip` : ''}
                </div>
              </div>
            </div>
          </Card>

          <Card title="Price + Buy / Sell Signals" actions={<ZoomControls zoomIn={priceZoom.zoomIn} zoomOut={priceZoom.zoomOut} reset={priceZoom.reset} />}>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={priceZoom.visibleData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis
                    dataKey="time"
                    tickFormatter={(t) => new Date(t).toLocaleDateString()}
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                    minTickGap={30}
                  />
                  <YAxis
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                    tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                    labelFormatter={(label) => new Date(String(label)).toLocaleString()}
                    formatter={(value, name) => [name === 'close' ? formatUSD(Number(value)) : `$${Number(value).toLocaleString()}`, name as string]}
                  />
                  <Line type="monotone" dataKey="close" stroke="#38bdf8" strokeWidth={2} dot={false} name="Price" />
                  <Line
                    dataKey="buy"
                    stroke="transparent"
                    dot={{ r: 5, fill: '#10b981' }}
                    isAnimationActive={false}
                    name="Buy"
                  />
                  <Line
                    dataKey="sell"
                    stroke="transparent"
                    dot={{ r: 5, fill: '#ef4444' }}
                    isAnimationActive={false}
                    name="Sell"
                  />
                  <Brush
                    dataKey="close"
                    startIndex={0}
                    endIndex={Math.max(0, priceZoom.visibleData.length - 1)}
                    onChange={priceZoom.onBrushChange}
                    height={30}
                    travellerWidth={8}
                    stroke="#38bdf8"
                    fill="rgba(56, 189, 248, 0.2)"
                    tickFormatter={(t: string) => new Date(t).toLocaleDateString()}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title={`Trades (${result!.trades.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-800">
                    <th className="text-left py-2 px-2" title={TRADE_HINTS.Entry}>Entry</th>
                    <th className="text-left py-2 px-2" title={TRADE_HINTS.Exit}>Exit</th>
                    <th className="text-left py-2 px-2" title={TRADE_HINTS.Side}>Side</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS['Entry $']}>Entry $</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS['Exit $']}>Exit $</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS.Size}>Size</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS['Net PnL']}>Net PnL</th>
                    <th className="text-left py-2 px-2">Exit Reason</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS.Return}>Return</th>
                    <th className="text-right py-2 px-2" title={TRADE_HINTS.Confidence}>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {result!.trades.slice(0, 50).map((t, i) => (
                    <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="py-2 px-2 text-gray-300">{new Date(t.entryTime).toLocaleString()}</td>
                      <td className="py-2 px-2 text-gray-300">{new Date(t.exitTime).toLocaleString()}</td>
                      <td className="py-2 px-2">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${
                            t.side === 'LONG' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                          }`}
                        >
                          {t.side}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right text-gray-300">{t.entryPrice.toLocaleString()}</td>
                      <td className="py-2 px-2 text-right text-gray-300">{t.exitPrice.toLocaleString()}</td>
                      <td className="py-2 px-2 text-right text-gray-300">{t.sizeCoin.toFixed(6)}</td>
                      <td className={`py-2 px-2 text-right font-medium ${t.netPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatUSD(t.netPnl)}
                      </td>
                      <td className="py-2 px-2 text-gray-300">{t.exitReason.replaceAll('_', ' ')}</td>
                      <td className={`py-2 px-2 text-right ${t.returnPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatPct(t.returnPct)}
                      </td>
                      <td className="py-2 px-2 text-right text-gray-300">{t.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  positive,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  positive?: boolean;
}) {
  const color =
    positive === undefined ? 'text-violet-400' : positive ? 'text-emerald-400' : 'text-red-400';
  return (
    <div
      className="bg-[#11131a] border border-gray-800 rounded-xl p-4 cursor-help"
      title={STAT_HINTS[label]}
    >
      <div className="flex items-center gap-2 text-gray-400 mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}
