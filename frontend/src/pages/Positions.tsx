import { useCallback, useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { Card } from '../components/Card';
import { fetchPositions, fetchOrders, closePosition } from '../services/api';
import { useWallet } from '../context/WalletContext';
import type { Position, Order } from '../types';

export function Positions() {
  const { selectedWallet } = useWallet();
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    const walletId = selectedWallet?.id;
    Promise.all([fetchPositions(walletId), fetchOrders(walletId)])
      .then(([p, o]) => {
        setPositions(p);
        setOrders(o);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'));
  }, [selectedWallet]);

  useEffect(() => {
    load();
  }, [load]);

  const handleClose = async (positionId: string) => {
    if (!selectedWallet) return;
    setLoading(true);
    setError('');
    try {
      await closePosition({ positionId, walletId: selectedWallet.id, mode: 'paper' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Close failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Positions & Orders</h1>
        <p className="text-sm text-gray-400 mt-1">Open positions, working orders, and fill history</p>
      </div>

      {!selectedWallet && (
        <div className="text-sm text-amber-400">Select an active wallet from the sidebar to view positions.</div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm">{error}</div>
      )}

      <Card>
        <h2 className="text-lg font-medium mb-4">Open Positions</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">Market</th>
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
                  <td className={`py-3 ${pos.side === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}`}>{pos.side}</td>
                  <td className="py-3">{pos.size.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td className="py-3 text-gray-400">${pos.entryPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="py-3 text-gray-400">${pos.markPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className={`py-3 font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString(undefined, { maximumFractionDigits: 4 })} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
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
              {positions.length === 0 && (
                <tr><td colSpan={9} className="py-4 text-gray-500">No open positions.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-medium mb-4">Orders</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
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
