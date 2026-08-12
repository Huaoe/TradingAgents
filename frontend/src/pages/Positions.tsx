import { useEffect, useState } from 'react';
import { Card } from '../components/Card';
import { fetchPositions, fetchOrders } from '../services/api';
import type { Position, Order } from '../types';

export function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    Promise.all([fetchPositions(), fetchOrders()]).then(([p, o]) => {
      setPositions(p);
      setOrders(o);
    });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Positions & Orders</h1>
        <p className="text-sm text-gray-400 mt-1">Open positions, working orders, and fill history</p>
      </div>

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
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {positions.map((pos) => (
                <tr key={pos.symbol}>
                  <td className="py-3 font-medium">{pos.symbol}</td>
                  <td className={`py-3 ${pos.side === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}`}>{pos.side}</td>
                  <td className="py-3">{pos.size}</td>
                  <td className="py-3 text-gray-400">${pos.entryPrice.toLocaleString()}</td>
                  <td className="py-3 text-gray-400">${pos.markPrice.toLocaleString()}</td>
                  <td className={`py-3 font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
                  </td>
                  <td className="py-3">{pos.leverage}x</td>
                  <td className="py-3 text-gray-400">{pos.liquidationPrice ? `$${pos.liquidationPrice.toLocaleString()}` : '-'}</td>
                </tr>
              ))}
              {positions.length === 0 && (
                <tr><td colSpan={8} className="py-4 text-gray-500">No open positions.</td></tr>
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
                  <td className="py-3">{order.size}</td>
                  <td className="py-3 text-gray-400">${order.price.toLocaleString()}</td>
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
                  <td className="py-3 text-gray-500 text-xs">{order.timestamp}</td>
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
