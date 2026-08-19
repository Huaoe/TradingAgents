import { useCallback, useEffect, useState } from 'react';
import { Loader2, X, RefreshCcw, AlertTriangle, ShieldAlert } from 'lucide-react';
import { Card } from '../components/Card';
import {
  activateKillSwitch,
  cancelExchangeOrder,
  closePosition,
  fetchAccount,
  fetchExchangeOrders,
  fetchPositions,
  fetchOrders,
  fetchReconciliation,
  reconcileWallet,
} from '../services/api';
import { useWallet } from '../context/useWallet';
import type {
  ExchangeOrder,
  Account,
  KillSwitchResult,
  Position,
  Order,
  ReconciliationResult,
} from '../types';

function exchangeOrderId(order: ExchangeOrder): string {
  return String(order.oid ?? order.orderId ?? '');
}

function exchangeOrderSymbol(order: ExchangeOrder): string {
  return String(order.coin ?? order.symbol ?? '-');
}

function exchangeOrderText(order: ExchangeOrder, ...keys: string[]): string {
  for (const key of keys) {
    const value = order[key];
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return '-';
}

function protectiveMeta(position: Position, orders: Order[]): Record<string, unknown> | null {
  return orders.find((order) => order.id === position.orderId)?.meta ?? null;
}

function numericMetaValue(meta: Record<string, unknown> | null, key: string): number | null {
  const value = meta?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function ProtectiveDetails({ position }: { position: Position }) {
  const hasLevels =
    position.stopPrice !== null ||
    position.takeProfitPrice !== null ||
    position.trailingStopPct !== null;
  if (!hasLevels && !position.trailingUnsupported && position.protectiveStatus !== 'unprotected') {
    return null;
  }

  return (
    <div className="mt-2 space-y-1 text-xs">
      <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border ${
        position.protectiveStatus === 'unprotected'
          ? 'text-rose-300 border-rose-500/40 bg-rose-500/15'
          : 'text-sky-300 border-sky-500/20 bg-sky-500/10'
      }`}>
        {position.protectiveStatus === 'unprotected' && <ShieldAlert className="w-3 h-3" />}
        Protection: {position.protectiveStatus || 'disabled'}
      </div>
      {position.stopPrice !== null && (
        <div className="text-gray-400">Stop ${position.stopPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
      )}
      {position.takeProfitPrice !== null && (
        <div className="text-gray-400">Target ${position.takeProfitPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
      )}
      {position.trailingStopPct !== null && (
        <div className="text-gray-400">Trailing {(position.trailingStopPct * 100).toFixed(2)}%</div>
      )}
      {position.trailingUnsupported && (
        <div className="text-amber-300">
          Hyperliquid cannot enforce a trailing stop on live positions; this leg is not active.
        </div>
      )}
    </div>
  );
}

type ActionModalState =
  | { kind: 'close'; positionId: string; symbol: string; mode: 'paper' | 'live' }
  | { kind: 'cancel'; orderId: string; symbol: string }
  | { kind: 'kill'; mode: 'paper' | 'live' };

function ActionModal({
  action,
  password,
  setPassword,
  loading,
  error,
  onClose,
  onConfirm,
}: {
  action: ActionModalState | null;
  password: string;
  setPassword: (value: string) => void;
  loading: boolean;
  error: string;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (!action) return null;

  const isLiveAction = action.kind === 'cancel' ? true : action.mode === 'live';
  const requiresPassword =
    isLiveAction;
  const title = action.kind === 'close'
    ? `Close ${action.symbol} position`
    : action.kind === 'cancel'
      ? `Cancel ${action.symbol} order`
      : `Activate ${action.mode} kill switch`;
  const description = action.kind === 'close'
    ? `This will close the selected ${action.mode} ${action.symbol} position.`
    : action.kind === 'cancel'
      ? `This will cancel resting exchange order ${action.orderId} for ${action.symbol}.`
      : action.mode === 'live'
        ? "This will cancel all resting exchange orders, close every open live position, and disable this wallet's live gate."
        : "This will close every open paper position and disable this wallet's live gate. Paper execution does not create exchange orders.";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
      <div className="bg-[#11131a] border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-xl">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <AlertTriangle className={`w-5 h-5 ${isLiveAction ? 'text-rose-400' : 'text-amber-400'}`} />
          {title}
        </h2>
        <p className="text-sm text-gray-300 mb-5">{description}</p>
        {requiresPassword && (
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-400 mb-1">Master Password</label>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              placeholder="Required for live actions"
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
            className="flex-1 px-4 py-2 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 disabled:opacity-50 text-sm font-medium"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || (requiresPassword && !password)}
            className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium disabled:opacity-50"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

function KillSwitchOutcomes({ result }: { result: KillSwitchResult }) {
  const outcomes = [...result.orders, ...result.positions];
  return (
    <div className="mt-4 space-y-2">
      <h3 className="text-sm font-medium text-gray-200">Kill-switch outcomes</h3>
      {outcomes.length === 0 && <p className="text-sm text-gray-500">No orders or positions required action.</p>}
      {outcomes.map((outcome, index) => (
        <div
          key={`${outcome.positionId || outcome.orderId || 'outcome'}-${index}`}
          className={`rounded border px-3 py-2 text-xs ${
            outcome.status === 'error'
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
              : 'border-gray-700 bg-gray-900/40 text-gray-300'
          }`}
        >
          <span className="font-medium">{outcome.positionId ? 'Position' : 'Order'}</span>
          {' '}
          {outcome.positionId || outcome.orderId || '-'}: {outcome.status}
          {outcome.symbol && ` (${outcome.symbol})`}
          {outcome.error && <span className="ml-2">{outcome.error}</span>}
        </div>
      ))}
    </div>
  );
}

export function Positions() {
  const { selectedWallet } = useWallet();
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [exchangeOrders, setExchangeOrders] = useState<ExchangeOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [exchangeOrderError, setExchangeOrderError] = useState('');
  const [reconciliation, setReconciliation] = useState<ReconciliationResult | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [killMode, setKillMode] = useState<'paper' | 'live'>('paper');
  const [killResult, setKillResult] = useState<KillSwitchResult | null>(null);
  const [actionModal, setActionModal] = useState<ActionModalState | null>(null);
  const [actionPassword, setActionPassword] = useState('');
  const [actionModalError, setActionModalError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const walletId = selectedWallet?.id;
      if (!walletId) return;
      const [a, p, o, r] = await Promise.all([
        fetchAccount(walletId),
        fetchPositions(walletId),
        fetchOrders(walletId),
        fetchReconciliation(walletId),
      ]);
      setAccount(a);
      setPositions(p);
      setOrders(o);
      setReconciliation(r);
      try {
        setExchangeOrders(await fetchExchangeOrders(walletId));
        setExchangeOrderError('');
      } catch (err) {
        setExchangeOrders([]);
        setExchangeOrderError(
          a.mode === 'live'
            ? err instanceof Error ? err.message : 'Exchange orders unavailable'
            : '',
        );
      }
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
    setAccount(null);
    setKillMode('paper');
    setKillResult(null);
  }, [selectedWallet?.id]);

  const accountMode = account?.mode;
  useEffect(() => {
    if (accountMode) setKillMode(accountMode === 'live' ? 'live' : 'paper');
  }, [accountMode]);

  useEffect(() => {
    const interval = setInterval(() => {
      load();
    }, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const handleClose = async (positionId: string) => {
    if (!selectedWallet) return;
    const position = positions.find((item) => item.id === positionId);
    if (!position) return;
    setActionPassword('');
    setActionModalError('');
    setActionModal({
      kind: 'close',
      positionId,
      symbol: position.symbol,
      mode: position.mode,
    });
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

  const handleCancelExchangeOrder = async (order: ExchangeOrder) => {
    if (!selectedWallet) return;
    const orderId = exchangeOrderId(order);
    const symbol = exchangeOrderSymbol(order);
    if (!orderId || symbol === '-') {
      setError('This exchange order has no cancellable symbol or order ID.');
      return;
    }
    setActionPassword('');
    setActionModalError('');
    setActionModal({ kind: 'cancel', orderId, symbol });
  };

  const handleKillSwitch = async () => {
    if (!selectedWallet) return;
    setActionPassword('');
    setActionModalError('');
    setActionModal({ kind: 'kill', mode: killMode });
  };

  const closeActionModal = () => {
    if (actionLoading) return;
    setActionModal(null);
    setActionPassword('');
    setActionModalError('');
  };

  const confirmActionModal = async () => {
    if (!actionModal || !selectedWallet) return;
    const masterPassword = actionPassword || undefined;
    setActionLoading(true);
    setActionModalError('');
    try {
      if (actionModal.kind === 'close') {
        await closePosition({
          positionId: actionModal.positionId,
          walletId: selectedWallet.id,
          mode: actionModal.mode,
          masterPassword,
        });
      } else if (actionModal.kind === 'cancel') {
        await cancelExchangeOrder({
          walletId: selectedWallet.id,
          symbol: actionModal.symbol,
          orderId: actionModal.orderId,
          masterPassword: actionPassword,
        });
      } else {
        setKillResult(await activateKillSwitch({
          walletId: selectedWallet.id,
          mode: actionModal.mode,
          masterPassword,
        }));
      }
      await load();
      setActionModal(null);
      setActionPassword('');
    } catch (err) {
      setActionModalError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setActionLoading(false);
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
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-medium">Kill switch</h2>
            <p className="text-xs text-gray-500 mt-1">Stop new risk before cancelling and flattening.</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={killMode}
              onChange={(event) => setKillMode(event.target.value as 'paper' | 'live')}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm"
            >
              <option value="live">Live</option>
              <option value="paper">Paper</option>
            </select>
            <button
              onClick={handleKillSwitch}
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-rose-700 hover:bg-rose-600 disabled:opacity-60 text-sm font-medium"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
              Activate kill switch
            </button>
          </div>
        </div>
        {killResult && <KillSwitchOutcomes result={killResult} />}
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
                  <td className="py-3 font-medium align-top">
                    {pos.symbol}
                    <ProtectiveDetails position={pos} />
                  </td>
                  <td className="py-3">
                    <span className={`text-xs px-2 py-0.5 rounded border ${
                      pos.mode === 'live'
                        ? 'text-rose-300 border-rose-500/20 bg-rose-500/10'
                        : 'text-emerald-300 border-emerald-500/20 bg-emerald-500/10'
                    }`}>
                      {pos.mode}
                    </span>
                  </td>
                  <td className={`py-3 align-top ${pos.side === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}`}>{pos.side}</td>
                  <td className="py-3 align-top">{pos.size.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td className="py-3 text-gray-400 align-top">${pos.entryPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="py-3 text-gray-400 align-top">${pos.markPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className={`py-3 font-medium align-top ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString(undefined, { maximumFractionDigits: 4 })} ({pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%)
                    <span className="ml-2 text-xs text-gray-500">({pos.pnlSource || 'mark_price'})</span>
                  </td>
                  <td className="py-3 align-top">{pos.leverage}x</td>
                  <td className="py-3 text-gray-400 align-top">{pos.liquidationPrice ? `$${pos.liquidationPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}` : '-'}</td>
                  <td className="py-3 align-top">
                    <button
                      onClick={() => handleClose(pos.id)}
                      disabled={loading || actionLoading}
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
        <h2 className="text-lg font-medium mb-4">Closed Positions</h2>
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm text-left min-w-[760px]">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">Market</th>
                <th className="pb-3 font-medium">Mode</th>
                <th className="pb-3 font-medium">Exit</th>
                <th className="pb-3 font-medium">Trigger / Fill</th>
                <th className="pb-3 font-medium">PnL</th>
                <th className="pb-3 font-medium">Closed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {positions.filter((position) => position.status !== 'open').map((pos) => {
                const meta = protectiveMeta(pos, orders);
                const trigger = numericMetaValue(meta, 'protectiveTriggerPrice');
                const fill = numericMetaValue(meta, 'protectiveFillPrice');
                return (
                  <tr key={pos.id}>
                    <td className="py-3 font-medium">{pos.symbol}</td>
                    <td className="py-3 text-xs text-gray-400">{pos.mode}</td>
                    <td className="py-3 text-gray-300">{pos.exitReason || 'signal'}</td>
                    <td className="py-3 text-gray-400">
                      {trigger !== null || fill !== null
                        ? `Trigger ${trigger !== null ? `$${trigger.toFixed(4)}` : '-'} · Fill ${fill !== null ? `$${fill.toFixed(4)}` : '-'}`
                        : '-'}
                    </td>
                    <td className={`py-3 ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(4)}
                    </td>
                    <td className="py-3 text-xs text-gray-500">
                      {pos.closedAt ? new Date(pos.closedAt).toLocaleString() : '-'}
                    </td>
                  </tr>
                );
              })}
              {positions.filter((position) => position.status !== 'open').length === 0 && (
                <tr><td colSpan={6} className="py-4 text-gray-500">No closed positions.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-medium mb-1">Resting Exchange Orders</h2>
        <p className="text-xs text-gray-500 mb-4">Live wallet orders only; paper execution has no exchange orders.</p>
        {exchangeOrderError && <p className="mb-3 text-sm text-amber-300">{exchangeOrderError}</p>}
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm text-left min-w-[640px]">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">ID</th>
                <th className="pb-3 font-medium">Market</th>
                <th className="pb-3 font-medium">Side</th>
                <th className="pb-3 font-medium">Size</th>
                <th className="pb-3 font-medium">Price</th>
                <th className="pb-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {exchangeOrders.map((order, index) => (
                <tr key={`${exchangeOrderId(order)}-${index}`}>
                  <td className="py-3 font-mono text-xs text-gray-400">{exchangeOrderId(order) || '-'}</td>
                  <td className="py-3 font-medium">{exchangeOrderSymbol(order)}</td>
                  <td className="py-3 text-gray-300">{exchangeOrderText(order, 'side', 'dir')}</td>
                  <td className="py-3 text-gray-300">{exchangeOrderText(order, 'sz', 'size')}</td>
                  <td className="py-3 text-gray-400">{exchangeOrderText(order, 'limitPx', 'price')}</td>
                  <td className="py-3">
                    <button
                      onClick={() => handleCancelExchangeOrder(order)}
                      disabled={loading || actionLoading}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-amber-600/20 text-amber-300 hover:bg-amber-600/30 text-xs font-medium disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </td>
                </tr>
              ))}
              {exchangeOrders.length === 0 && (
                <tr><td colSpan={6} className="py-4 text-gray-500">No resting exchange orders. Paper positions do not create exchange orders.</td></tr>
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
      <ActionModal
        action={actionModal}
        password={actionPassword}
        setPassword={setActionPassword}
        loading={actionLoading}
        error={actionModalError}
        onClose={closeActionModal}
        onConfirm={confirmActionModal}
      />
    </div>
  );
}
