import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Card } from '../components/Card';
import { fetchAccount, fetchSignals, fetchPositions } from '../services/api';
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
  const [account, setAccount] = useState<Account | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    Promise.all([fetchAccount(), fetchSignals(), fetchPositions()]).then(([a, s, p]) => {
      setAccount(a);
      setSignals(s.slice(0, 3));
      setPositions(p);
    });
  }, []);

  if (!account) return <div className="p-8 text-gray-400">Loading dashboard...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-gray-400 mt-1">Hyperliquid trading agent overview</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <DollarSign className="w-4 h-4" />
          <span>Wallet: {account.wallet}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Total Value" value={`$${account.totalValue.toLocaleString()}`} sub={`$${account.available.toLocaleString()} available`} />
        <Stat label="Unrealized PnL" value={`+$${account.unrealizedPnl.toLocaleString()}`} positive />
        <Stat label="Daily PnL" value={`+$${account.dailyPnl.toLocaleString()}`} positive />
        <Stat label="Margin Used" value={`$${account.marginUsed.toLocaleString()}`} sub={`${((account.marginUsed / account.totalValue) * 100).toFixed(1)}% of account`} />
      </div>

      <Card>
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
                  <div className="text-xs text-gray-500">{sig.timestamp}</div>
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
              <div key={pos.symbol} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30 border border-gray-800">
                <div>
                  <div className="font-medium">{pos.symbol} <span className="text-xs text-gray-400">{pos.side} {pos.leverage}x</span></div>
                  <div className="text-xs text-gray-500">Entry ${pos.entryPrice.toLocaleString()}</div>
                </div>
                <div className={`text-sm font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
