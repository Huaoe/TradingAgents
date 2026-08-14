import { useCallback, useEffect, useState } from 'react';
import { Bell, Check } from 'lucide-react';
import { Card } from '../components/Card';
import { useWallet } from '../context/useWallet';
import { fetchAlerts, markAlertRead, markAllAlertsRead } from '../services/api';
import type { Alert } from '../types';

const severityClasses: Record<string, string> = {
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  error: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
};

export function Alerts() {
  const { selectedWallet } = useWallet();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const load = useCallback(async () => {
    const walletId = selectedWallet?.id;
    const data = await fetchAlerts(walletId, filter === 'unread');
    setAlerts(data);
  }, [selectedWallet, filter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRead = async (id: string) => {
    await markAlertRead(id);
    load();
  };

  const handleReadAll = async () => {
    await markAllAlertsRead(selectedWallet?.id);
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Alerts</h1>
          <p className="text-sm text-gray-400 mt-1">Signal, position, and risk notifications</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as 'all' | 'unread')}
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-violet-500"
          >
            <option value="all">All</option>
            <option value="unread">Unread</option>
          </select>
          <button
            onClick={handleReadAll}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
          >
            <Check className="w-4 h-4" />
            Mark all read
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {alerts.length === 0 && (
          <Card>
            <div className="flex items-center gap-3 text-gray-500 py-6">
              <Bell className="w-5 h-5" />
              <span>No alerts yet.</span>
            </div>
          </Card>
        )}
        {alerts.map((alert) => (
          <Card
            key={alert.id}
            className={`flex items-start justify-between gap-4 border ${severityClasses[alert.severity] || 'border-gray-800'} ${!alert.read ? 'bg-gray-800/20' : ''}`}
          >
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-medium uppercase tracking-wider ${severityClasses[alert.severity]?.split(' ')[1] || 'text-gray-400'}`}>
                  {alert.type}
                </span>
                <span className="text-xs text-gray-500">{new Date(alert.timestamp).toLocaleString()}</span>
              </div>
              <p className={`text-sm ${!alert.read ? 'text-white' : 'text-gray-300'}`}>{alert.message}</p>
            </div>
            {!alert.read && (
              <button
                onClick={() => handleRead(alert.id)}
                className="p-2 rounded-lg hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
                aria-label="Mark read"
              >
                <Check className="w-4 h-4" />
              </button>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
