import { useCallback, useEffect, useState } from 'react';
import { Loader2, X, RefreshCcw, AlertTriangle } from 'lucide-react';
import { Card } from '../components/Card';
import { fetchPositions, fetchOrders, closePosition, fetchReconciliation, reconcileWallet } from '../services/api';
import { useWallet } from '../context/useWallet';
import type { Position, Order, ReconciliationResult } from '../types';

export function Positions() {
  const { selectedWallet } = useWallet();
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reconciliation, setReconciliation] = useState<ReconciliationResult | null>(null);
  const [reconciling, setReconciling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const walletId = selectedWallet?.id;
      if (!walletId) return;
      const [p, o, r] = await Promise.all([fetchPositions(walletId), fetchOrders(walletId), fetchReconciliation(walletId)]);
      setPositions(p);
      setOrders(o);
      setReconciliation(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [selectedWallet]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(() => {
      load();
    }, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const handleClose = async (positionId: string) => {
    if (!selectedWallet) return;
    setLoading(true);
    setError('');
    try {
      const position = positions.find((item) => item.id === positionId);
      await closePosition({ positionId, walletId: selectedWallet.id, mode: position?.mode || 'paper' });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Close failed');
    } finally {
      setLoading(false);
    }
  };

  const handleReconcile = async () => {
    if (!selectedWallet) return;
    setReconciling(true);
    setError('');
    try {
      setReconciliation(await reconcileWallet(selectedWallet.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reconciliation failed');
    } finally {
      setReconciling(false);
    }
  };

  if (!selectedWallet) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Positions & Orders</h1>
        <div className="text-sm text-amber-400">Select an active wallet from the sidebar to view positions.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Positions & Orders</h1>
          <p className="text-sm text-gray-400 mt-1">Open positions, working orders, and fill history</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-60 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <div className="flex-1">{error}</div>
        </div>
      )}

      <Card>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium">Exchange Reconciliation</h2>
            <p className="text-xs text-gray-500 mt-1">
              {reconciliation
                ? `Last run ${new Date(reconciliation.timestamp).toLocaleString()}`
                : 'No reconciliation has run yet.'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-2 py-1 rounded border ${
              reconciliation?.status === 'ok'
                ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10'
                : reconciliation?.status === 'not_applicable'
                  ? 'text-sky-300 border-sky-500/20 bg-sky-500/10'
                : reconciliation?.status === 'unavailable'
                  ? 'text-amber-400 border-amber-500/20 bg-amber-500/10'
                  : 'text-rose-400 border-rose-500/20 bg-rose-500/10'
            }`}>
              {reconciliation?.status || 'not run'}
            </span>
            <button
              onClick={handleReconcile}
              disabled={reconciling}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-60 text-sm"
            >
              {reconciling ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
              Reconcile now
            </button>
          </div>
        </div>
        {reconciliation?.error && (
          <p className="mt-3 text-sm text-amber-300">{reconciliation.error}</p>
        )}
        {reconciliation && reconciliation.divergences.length > 0 && (
          <ul className="mt-4 space-y-2 text-sm">
            {reconciliation.divergences.map((divergence, index) => (
              <li key={`${divergence.type}-${divergence.symbol || index}`} className="text-gray-300">
                <span className="text-rose-300">{divergence.type}</span>: {divergence.message}
              </li>
            ))}
          </ul>
        )}
        {reconciliation?.status === 'ok' && (
          <p className="mt-3 text-sm text-emerald-300">Local live positions match the exchange.</p>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-medium mb-4">Open Positions</h2>
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm text-left min-w-[640px]">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">Market</th>
                <th className="pb-3 font-medium">Mode</th>
                <th className="pb-3 font-medium">Side</th>
                <th className="pb-3 font-medium">Size</th>
                <th className="pb-3 font-medium">Entry</th>
                <th className="pb-3 font-medium">Mark</th>
                <th className="pb-3 font-medium">PnL</th>
                <th className="pb-3 font-medium">Leverage</th>
                <th className="pb-3 font-medium">Liq. Price</th>
                <th className="pb-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {positions.filter((p) => p.status === 'open').map((pos) => (
                <tr key={pos.id}>
                  <td className="py-3 font-medium">{pos.symbol}</td>
                  <td className="py-3">
                    <span className={`text-xs px-2 py-0.5 rounded border ${
                      pos.mode === 'live'
                        ? 'text-rose-300 border-rose-500/20 bg-rose-500/10'
                        : 'text-emerald-300 border-emerald-500/20 bg-emerald-500/10'
                    }`}>
                      {pos.mode}
                    </span>
                  </td>
                  <td className={`py-3 ${pos.side === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}`}>{pos.side}</td>
                  <td className="py-3">{pos.size.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td className="py-3 text-gray-400">${pos.entryPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="py-3 text-gray-400">${pos.markPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className={`py-3 font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString(undefined, { maximumFractionDigits: 4 })} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
                    <span className="ml-2 text-xs text-gray-500">({pos.pnlSource || 'mark_price'})</span>
                  </td>
                  <td className="py-3">{pos.leverage}x</td>
                  <td className="py-3 text-gray-400">{pos.liquidationPrice ? `$${pos.liquidationPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}` : '-'}</td>
                  <td className="py-3">
                    <button
                      onClick={() => handleClose(pos.id)}
                      disabled={loading}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 text-xs font-medium disabled:opacity-50"
                    >
                      {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <X className="w-3 h-3" />}
                      Close
                    </button>
                  </td>
                </tr>
              ))}
              {positions.filter((p) => p.status === 'open').length === 0 && (
                <tr><td colSpan={10} className="py-4 text-gray-500">No open positions.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-medium mb-4">Orders</h2>
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm text-left min-w-[600px]">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">ID</th>
                <th className="pb-3 font-medium">Market</th>
                <th className="pb-3 font-medium">Side</th>
                <th className="pb-3 font-medium">Size</th>
                <th className="pb-3 font-medium">Price</th>
                <th className="pb-3 font-medium">Type</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {orders.map((order) => (
                <tr key={order.id}>
                  <td className="py-3 font-mono text-xs text-gray-400">{order.id}</td>
                  <td className="py-3 font-medium">{order.symbol}</td>
                  <td className={`py-3 ${order.side === 'Buy' ? 'text-emerald-400' : 'text-rose-400'}`}>{order.side}</td>
                  <td className="py-3">{order.size.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td className="py-3 text-gray-400">${order.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="py-3 text-gray-400">{order.type}</td>
                  <td className="py-3">
                    <span className={`text-xs px-2 py-0.5 rounded border ${
                      order.status === 'filled' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                      order.status === 'open' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                      'bg-gray-700 text-gray-400 border-gray-600'
                    }`}>
                      {order.status}
                    </span>
                  </td>
                  <td className="py-3 text-gray-500 text-xs">{new Date(order.timestamp).toLocaleString()}</td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr><td colSpan={8} className="py-4 text-gray-500">No orders.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
