import { useCallback, useEffect, useMemo, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign, Shield, Loader2, RefreshCcw, AlertTriangle } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Card } from '../components/Card';
import { fetchAccount, fetchSignals, fetchPositions, fetchPortfolioHistory } from '../services/api';
import { useWallet } from '../context/useWallet';
import type { Account, Signal, Position, PortfolioHistoryPoint } from '../types';

function Stat({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400">{label}</span>
        {positive === undefined ? <Activity className="w-4 h-4 text-gray-500" /> : positive ? <TrendingUp className="w-4 h-4 text-emerald-400" /> : <TrendingDown className="w-4 h-4 text-rose-400" />}
      </div>
      <div className="text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </Card>
  );
}

function SkeletonStat() {
  return (
    <Card>
      <div className="h-4 w-20 bg-gray-800 rounded mb-2 animate-pulse" />
      <div className="h-8 w-32 bg-gray-800 rounded animate-pulse" />
    </Card>
  );
}

export function Dashboard() {
  const { selectedWallet } = useWallet();
  const [account, setAccount] = useState<Account | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [history, setHistory] = useState<PortfolioHistoryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const walletId = selectedWallet?.id;
      const [a, s, p, h] = await Promise.all([
        fetchAccount(walletId),
        fetchSignals(),
        fetchPositions(walletId),
        fetchPortfolioHistory(walletId, 100),
      ]);
      setAccount(a);
      setSignals(s.slice(0, 3));
      setPositions(p.filter((pos) => pos.status === 'open'));
      setHistory(h);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [selectedWallet]);

  useEffect(() => {
    load();
  }, [load]);

  const equityData = useMemo(
    () => history.map((point) => ({ time: point.timestamp, equity: point.totalValue })),
    [history]
  );

  if (!account && loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-gray-800 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonStat key={i} />)}
        </div>
        <div className="h-64 bg-gray-800 rounded animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <div className="flex-1">{error}</div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
          Retry
        </button>
      </div>
    );
  }

  if (!account) {
    return <div className="p-8 text-gray-400">No account data available.</div>;
  }

  const walletLabel = account.wallet || account.walletId || 'Paper';
  const unrealizedPositive = account.unrealizedPnl >= 0;
  const dailyPositive = account.dailyPnl >= 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-1">Hyperliquid trading agent overview</p>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <span className={`px-2 py-1 rounded-full border text-xs ${account.mode === 'live' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
            {account.mode === 'live' ? 'LIVE' : 'PAPER'}
          </span>
          <DollarSign className="w-4 h-4" />
          <span className="truncate max-w-[140px] sm:max-w-none">Wallet: {walletLabel}</span>
          <button
            onClick={load}
            disabled={loading}
            className="p-1.5 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50"
            aria-label="Refresh"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total Value" value={`$${account.totalValue.toLocaleString()}`} sub={`$${account.available.toLocaleString()} available`} />
        <Stat label="Unrealized PnL" value={`${unrealizedPositive ? '+' : ''}$${account.unrealizedPnl.toLocaleString()}`} positive={unrealizedPositive} />
        <Stat label="Daily PnL" value={`${dailyPositive ? '+' : ''}$${account.dailyPnl.toLocaleString()}`} positive={dailyPositive} />
        <Stat label="Margin Used" value={`$${account.marginUsed.toLocaleString()}`} sub={`${account.totalValue ? ((account.marginUsed / account.totalValue) * 100).toFixed(1) : '0.0'}% of account`} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Stat
          label="LLM Spend"
          value={`$${(account.llmSpend ?? 0).toFixed(4)}`}
          sub={`${((account.llmTokensIn ?? 0) + (account.llmTokensOut ?? 0)).toLocaleString()} tokens @ configured rates`}
        />
        <Stat
          label="LLM Tokens"
          value={`${((account.llmTokensIn ?? 0) + (account.llmTokensOut ?? 0)).toLocaleString()}`}
          sub={`${(account.llmTokensIn ?? 0).toLocaleString()} in / ${(account.llmTokensOut ?? 0).toLocaleString()} out`}
        />
        <Stat label="LLM Calls" value={`${account.llmCalls ?? 0}`} sub="Total model invocations" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <h2 className="text-lg font-medium mb-4">Equity Curve (Paper)</h2>
          <div className="h-64">
            {equityData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-gray-500">
                No equity history yet. Points are recorded every minute.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="time" stroke="#6b7280" fontSize={12} tickFormatter={(t) => new Date(t).toLocaleDateString()} />
                  <YAxis stroke="#6b7280" fontSize={12} domain={['auto', 'auto']} tickFormatter={(v) => `$${Number(v).toLocaleString()}`} />
                  <Tooltip contentStyle={{ backgroundColor: '#11131a', border: '1px solid #374151' }} labelFormatter={(label) => new Date(String(label)).toLocaleString()} formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Equity']} />
                  <Area type="monotone" dataKey="equity" stroke="#8b5cf6" fillOpacity={1} fill="url(#colorValue)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-violet-400" />
            <h2 className="text-lg font-medium">Risk Snapshot</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Open positions</span>
              <span className="font-medium">{account.openPositions ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Total notional</span>
              <span className="font-medium">${account.totalNotional?.toLocaleString() ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Max exposure</span>
              <span className="font-medium">{account.maxExposureSymbol || '-'} (${account.maxExposureNotional?.toLocaleString() ?? 0})</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Max leverage</span>
              <span className="font-medium">{account.maxLeverage ?? 0}x</span>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <h2 className="text-lg font-medium mb-4">Recent Signals</h2>
          <div className="space-y-3">
            {signals.length === 0 && <p className="text-sm text-gray-500">No signals yet.</p>}
            {signals.map((sig) => (
              <div key={sig.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30 border border-gray-800">
                <div>
                  <div className="font-medium">
                    {sig.symbol} <span className={`ml-2 text-xs ${sig.action === 'BUY' ? 'text-emerald-400' : sig.action === 'SELL' ? 'text-rose-400' : 'text-amber-400'}`}>{sig.action}</span>
                  </div>
                  <div className="text-xs text-gray-500">{new Date(sig.timestamp).toLocaleString()}</div>
                </div>
                <div className="text-sm text-gray-300">{sig.confidence}% conf</div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-medium mb-4">Open Positions</h2>
          <div className="space-y-3">
            {positions.length === 0 && <p className="text-sm text-gray-500">No open positions.</p>}
            {positions.map((pos) => (
              <div key={pos.id} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30 border border-gray-800">
                <div>
                  <div className="font-medium">{pos.symbol} <span className="text-xs text-gray-400">{pos.side} {pos.leverage}x</span></div>
                  <div className="text-xs text-gray-500">Entry ${pos.entryPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
                </div>
                <div className={`text-sm font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString(undefined, { maximumFractionDigits: 4 })} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
