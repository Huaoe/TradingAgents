import { Loader2, AlertTriangle } from 'lucide-react';
import type { Signal, Wallet } from '../types';

interface ExecuteModalProps {
  isOpen: boolean;
  signal: Signal | null;
  wallet: Wallet | null;
  mode: 'paper' | 'live';
  orderType: 'market' | 'limit';
  setOrderType: (value: 'market' | 'limit') => void;
  limitPrice: string;
  setLimitPrice: (value: string) => void;
  tif: 'Alo' | 'Gtc' | 'Ioc';
  setTif: (value: 'Alo' | 'Gtc' | 'Ioc') => void;
  expireMinutes: string;
  setExpireMinutes: (value: string) => void;
  orderBookLoading: boolean;
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
  orderType,
  setOrderType,
  limitPrice,
  setLimitPrice,
  tif,
  setTif,
  expireMinutes,
  setExpireMinutes,
  orderBookLoading,
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

        <div className="space-y-3 mb-5">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Order type</label>
            <select
              value={orderType}
              onChange={(event) => setOrderType(event.target.value as 'market' | 'limit')}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
            >
              <option value="market">Market</option>
              <option value="limit">Limit / maker</option>
            </select>
          </div>
          {orderType === 'limit' && (
            <>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Limit price {orderBookLoading && '(loading book...)'}
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={limitPrice}
                  onChange={(event) => setLimitPrice(event.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                  placeholder="Best bid/ask"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Time in force</label>
                <select
                  value={tif}
                  onChange={(event) => setTif(event.target.value as 'Alo' | 'Gtc' | 'Ioc')}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                >
                  <option value="Alo">Alo — post-only / maker</option>
                  <option value="Gtc">Gtc — rest until cancelled</option>
                  <option value="Ioc">Ioc — fill now or cancel</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Expiry (minutes, optional)</label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={expireMinutes}
                  onChange={(event) => setExpireMinutes(event.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                  placeholder="No expiry"
                />
              </div>
              <p className="text-xs text-sky-300">
                Post-only orders rest to seek the maker fee. A crossing Alo price is rejected; paper fills at the limit when the mark touches it, with no queue model.
              </p>
              {mode === 'live' && (
                <p className="text-xs text-amber-300">
                  If a live limit order fills while unattended, protective triggers cannot be signed from the monitor and the resulting position will be marked unprotected.
                </p>
              )}
            </>
          )}
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
            {orderType === 'limit' ? 'Place Limit Order' : mode === 'live' ? 'Execute Live' : 'Execute Paper'}
          </button>
        </div>
      </div>
    </div>
  );
}
