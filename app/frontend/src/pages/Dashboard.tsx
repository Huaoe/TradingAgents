import { useCallback, useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign, Shield } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Card } from '../components/Card';
import { fetchAccount, fetchSignals, fetchPositions } from '../services/api';
import { useWallet } from '../context/WalletContext';
import { equityData } from '../data/mockData';
import type { Account, Signal, Position } from '../types';

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

export function Dashboard() {
  const { selectedWallet } = useWallet();
  const [account, setAccount] = useState<Account | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);

  const load = useCallback(() => {
    const walletId = selectedWallet?.id;
    Promise.all([fetchAccount(walletId), fetchSignals(), fetchPositions(walletId)]).then(([a, s, p]) => {
      setAccount(a);
      setSignals(s.slice(0, 3));
      setPositions(p.filter((pos) => pos.status === 'open'));
    });
  }, [selectedWallet]);

  useEffect(() => {
    load();
  }, [load]);

  if (!account) return <div className="p-8 text-gray-400">Loading dashboard...</div>;

  const walletLabel = account.wallet || account.walletId || 'Paper';
  const unrealizedPositive = account.unrealizedPnl >= 0;
  const dailyPositive = account.dailyPnl >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-1">Hyperliquid trading agent overview</p>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <span className={`px-2 py-1 rounded-full border text-xs ${account.mode === 'live' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
            {account.mode === 'live' ? 'LIVE' : 'PAPER'}
          </span>
          <DollarSign className="w-4 h-4" />
          <span>Wallet: {walletLabel}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total Value" value={`$${account.totalValue.toLocaleString()}`} sub={`$${account.available.toLocaleString()} available`} />
        <Stat label="Unrealized PnL" value={`${unrealizedPositive ? '+' : ''}$${account.unrealizedPnl.toLocaleString()}`} positive={unrealizedPositive} />
        <Stat label="Daily PnL" value={`${dailyPositive ? '+' : ''}$${account.dailyPnl.toLocaleString()}`} positive={dailyPositive} />
        <Stat label="Margin Used" value={`$${account.marginUsed.toLocaleString()}`} sub={`${((account.marginUsed / account.totalValue) * 100).toFixed(1)}% of account`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <h2 className="text-lg font-medium mb-4">Equity Curve (Paper)</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityData}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="day" stroke="#6b7280" fontSize={12} />
                <YAxis stroke="#6b7280" fontSize={12} domain={['auto', 'auto']} />
                <Tooltip contentStyle={{ backgroundColor: '#11131a', border: '1px solid #374151' }} />
                <Area type="monotone" dataKey="value" stroke="#8b5cf6" fillOpacity={1} fill="url(#colorValue)" />
              </AreaChart>
            </ResponsiveContainer>
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
