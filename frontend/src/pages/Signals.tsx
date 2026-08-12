import { useEffect, useState } from 'react';
import { Check, X, Bot } from 'lucide-react';
import { Card, Badge } from '../components/Card';
import { fetchSignals, acceptSignal, rejectSignal } from '../services/api';
import type { Signal } from '../types';

export function Signals() {
  const [signals, setSignals] = useState<Signal[]>([]);

  useEffect(() => {
    fetchSignals().then(setSignals);
  }, []);

  const updateStatus = (id: string, status: 'accepted' | 'rejected') => {
    const update = status === 'accepted' ? acceptSignal : rejectSignal;
    update(id).then(() => {
      setSignals((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s)));
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Signal Feed</h1>
        <p className="text-sm text-gray-400 mt-1">Review and act on TradingAgents signals</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {signals.map((sig) => (
          <Card key={sig.id} className="flex flex-col">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-violet-400" />
                <span className="font-semibold text-lg">{sig.symbol}</span>
                <Badge action={sig.action} />
              </div>
              <span className="text-xs text-gray-500">{sig.timestamp}</span>
            </div>

            <p className="text-sm text-gray-300 mb-4 flex-1">{sig.reasoning}</p>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm mb-4">
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Confidence</div>
                <div className="font-medium">{sig.confidence}%</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Size</div>
                <div className="font-medium">${sig.size}</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Leverage</div>
                <div className="font-medium">{sig.leverage ?? 1}x</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Entry</div>
                <div className="font-medium">${sig.entry.toLocaleString()}</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Stop</div>
                <div className="font-medium text-rose-400">${sig.stop.toLocaleString()}</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Target</div>
                <div className="font-medium text-emerald-400">${sig.target.toLocaleString()}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              {sig.agents.map((agent) => (
                <span key={agent} className="text-xs px-2 py-1 rounded-full bg-gray-800 text-gray-400 border border-gray-700">
                  {agent}
                </span>
              ))}
            </div>

            {sig.status === 'pending' ? (
              <div className="flex gap-3 mt-auto">
                <button
                  onClick={() => updateStatus(sig.id, 'accepted')}
                  className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
                >
                  <Check className="w-4 h-4" /> Accept
                </button>
                <button
                  onClick={() => updateStatus(sig.id, 'rejected')}
                  className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium transition-colors"
                >
                  <X className="w-4 h-4" /> Reject
                </button>
              </div>
            ) : (
              <div className={`text-sm font-medium text-center py-2 rounded-lg border ${sig.status === 'accepted' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5' : 'text-rose-400 border-rose-500/30 bg-rose-500/5'}`}>
                Signal {sig.status}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
