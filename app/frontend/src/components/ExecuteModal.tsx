import { Loader2, AlertTriangle } from 'lucide-react';
import type { Signal, Wallet } from '../types';

interface ExecuteModalProps {
  isOpen: boolean;
  signal: Signal | null;
  wallet: Wallet | null;
  mode: 'paper' | 'live';
  masterPassword: string;
  setMasterPassword: (value: string) => void;
  loading: boolean;
  error: string;
  onClose: () => void;
  onConfirm: () => void;
}

export function ExecuteModal({
  isOpen,
  signal,
  wallet,
  mode,
  masterPassword,
  setMasterPassword,
  loading,
  error,
  onClose,
  onConfirm,
}: ExecuteModalProps) {
  if (!isOpen || !signal) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
      <div className="bg-[#11131a] border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-xl">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <AlertTriangle className={`w-5 h-5 ${mode === 'live' ? 'text-rose-400' : 'text-emerald-400'}`} />
          {mode === 'live' ? 'Confirm Live Trade' : 'Confirm Paper Trade'}
        </h2>

        <div className="space-y-3 text-sm mb-6">
          <div className="flex justify-between">
            <span className="text-gray-400">Symbol</span>
            <span className="font-medium">{signal.symbol}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Side</span>
            <span className={`font-medium ${signal.action === 'BUY' ? 'text-emerald-400' : signal.action === 'SELL' ? 'text-rose-400' : 'text-amber-400'}`}>
              {signal.action}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Size</span>
            <span className="font-medium">${signal.size.toLocaleString()}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Leverage</span>
            <span className="font-medium">{signal.leverage ?? 1}x</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Wallet</span>
            <span className="font-medium">{wallet?.name ?? 'None'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Mode</span>
            <span className={`font-medium ${mode === 'live' ? 'text-rose-400' : 'text-emerald-400'}`}>{mode.toUpperCase()}</span>
          </div>
        </div>

        {mode === 'live' && (
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-400 mb-1">Master Password</label>
            <input
              type="password"
              value={masterPassword}
              onChange={(e) => setMasterPassword(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              placeholder="Required for live execution"
              autoFocus
            />
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 px-4 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 disabled:opacity-50 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || (mode === 'live' && !masterPassword)}
            className={`flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-50 ${
              mode === 'live' ? 'bg-rose-600 hover:bg-rose-500' : 'bg-emerald-600 hover:bg-emerald-500'
            }`}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {mode === 'live' ? 'Execute Live' : 'Execute Paper'}
          </button>
        </div>
      </div>
    </div>
  );
}
