import { useEffect, useState } from 'react';
import { Check, X, Bot, Loader2, Plus, Trash2, Sparkles } from 'lucide-react';
import { Card, Badge } from '../components/Card';
import { fetchSignals, fetchStrategies, createSignal, acceptSignal, rejectSignal, deleteSignal } from '../services/api';
import type { Signal, Strategy } from '../types';

export function Signals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [symbol, setSymbol] = useState('BTC');
  const [strategyId, setStrategyId] = useState('');
  const [useLlm, setUseLlm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    refresh();
    fetchStrategies().then((list) => {
      setStrategies(list);
      const saved = list.find((s) => !s.id.startsWith('template-'));
      if (saved) setStrategyId(saved.id);
    });
  }, []);

  const refresh = () => {
    fetchSignals().then(setSignals).catch(() => setSignals([]));
  };

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await createSignal({ symbol: symbol.toUpperCase(), strategyId: strategyId || undefined, useLlm });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate signal');
    } finally {
      setLoading(false);
    }
  }

  const updateStatus = async (id: string, status: 'accepted' | 'rejected') => {
    try {
      if (status === 'accepted') await acceptSignal(id);
      else await rejectSignal(id);
      setSignals((prev) => prev.map((s) => (s.id === id ? { ...s, status } : s)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Status update failed');
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteSignal(id);
      setSignals((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Signal Feed</h1>
        <p className="text-sm text-gray-400 mt-1">Generate and act on TradingAgents signals</p>
      </div>

      <Card title="Generate Signal">
        <form onSubmit={handleGenerate} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-400">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            />
          </div>
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
          <label className="flex items-center gap-2 text-sm text-gray-300 md:col-span-1 pb-2">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              className="rounded border-gray-700 bg-gray-900 text-violet-600"
            />
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" /> Use LLM (if key configured)
            </span>
          </label>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Generate
          </button>
        </form>
        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm">
            {error}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {signals.map((sig) => (
          <Card key={sig.id} className="flex flex-col">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-violet-400" />
                <span className="font-semibold text-lg">{sig.symbol}</span>
                <Badge action={sig.action} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{new Date(sig.timestamp).toLocaleString()}</span>
                <button
                  onClick={() => remove(sig.id)}
                  className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <p className="text-sm text-gray-300 mb-4 flex-1">{sig.reasoning}</p>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm mb-4">
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Confidence</div>
                <div className="font-medium">{sig.confidence}%</div>
              </div>
              <div className="bg-gray-800/30 rounded-lg p-2">
                <div className="text-gray-500 text-xs">Size</div>
                <div className="font-medium">${sig.size.toLocaleString()}</div>
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
        {signals.length === 0 && <div className="text-gray-500 text-sm">No signals yet. Generate one above.</div>}
      </div>
    </div>
  );
}
