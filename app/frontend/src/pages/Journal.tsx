import { useCallback, useEffect, useState } from 'react';
import { BookOpen } from 'lucide-react';
import { Card } from '../components/Card';
import { useWallet } from '../context/useWallet';
import { fetchJournal } from '../services/api';
import type { JournalEntry } from '../types';

export function Journal() {
  const { selectedWallet } = useWallet();
  const [entries, setEntries] = useState<JournalEntry[]>([]);

  const load = useCallback(async () => {
    const data = await fetchJournal(selectedWallet?.id);
    setEntries(data);
  }, [selectedWallet]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Trade Journal</h1>
        <p className="text-sm text-gray-400 mt-1">Closed trades with reflection notes</p>
      </div>

      <div className="space-y-3">
        {entries.length === 0 && (
          <Card>
            <div className="flex items-center gap-3 text-gray-500 py-6">
              <BookOpen className="w-5 h-5" />
              <span>No closed trades yet.</span>
            </div>
          </Card>
        )}
        {entries.map((entry) => (
          <Card key={entry.id} className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="font-medium">{entry.symbol}</span>
                <span className="text-xs text-gray-400">{entry.side} {entry.leverage}x</span>
              </div>
              <span className={`text-sm font-medium ${entry.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {entry.netPnl >= 0 ? '+' : ''}${entry.netPnl.toFixed(4)}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-gray-500 text-xs">Entry</div>
                <div>${entry.entryPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
              </div>
              <div>
                <div className="text-gray-500 text-xs">Exit</div>
                <div>${entry.exitPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
              </div>
              <div>
                <div className="text-gray-500 text-xs">Size</div>
                <div>{entry.size.toFixed(6)}</div>
              </div>
              <div>
                <div className="text-gray-500 text-xs">Fees</div>
                <div>${entry.fees.toFixed(4)}</div>
              </div>
            </div>
            {entry.reflection && (
              <div className="text-sm text-gray-300 bg-gray-800/30 p-3 rounded-lg border border-gray-800">
                <span className="text-gray-500 text-xs uppercase tracking-wider">Reflection</span>
                <p className="mt-1">{entry.reflection}</p>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
