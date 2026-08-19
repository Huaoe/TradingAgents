import type { Market, Signal, Position, Order, Account, Alert, JournalEntry, Strategy, StrategyInput, ModelCatalog, BacktestInput, BacktestResult, Wallet, WalletInput, Health, WalletUpdateInput, PortfolioHistoryPoint, StrategySearchInput, StrategySearchJob, ReconciliationResult, ExchangeOrder, KillSwitchResult } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<Health> {
  return api<Health>('/api/health');
}

export async function fetchMarkets(): Promise<Market[]> {
  return api<Market[]>('/api/markets');
}

export async function fetchSignals(): Promise<Signal[]> {
  return api<Signal[]>('/api/signals');
}

export async function fetchPositions(walletId?: string): Promise<Position[]> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  return api<Position[]>(`/api/positions${qs}`);
}

export async function fetchOrders(walletId?: string): Promise<Order[]> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  return api<Order[]>(`/api/orders${qs}`);
}

export async function fetchExchangeOrders(walletId: string): Promise<ExchangeOrder[]> {
  return api<ExchangeOrder[]>(`/api/exchange/orders?wallet_id=${encodeURIComponent(walletId)}`);
}

export interface CancelExchangeOrderInput {
  walletId: string;
  symbol: string;
  orderId: string;
  masterPassword?: string;
}

export async function cancelExchangeOrder(input: CancelExchangeOrderInput): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>('/api/exchange/orders/cancel', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export interface KillSwitchInput {
  walletId: string;
  mode: 'paper' | 'live';
  masterPassword?: string;
}

export async function activateKillSwitch(input: KillSwitchInput): Promise<KillSwitchResult> {
  return api<KillSwitchResult>('/api/kill-switch', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function fetchReconciliation(walletId: string): Promise<ReconciliationResult | null> {
  return api<ReconciliationResult | null>(`/api/reconcile?wallet_id=${encodeURIComponent(walletId)}`);
}

export async function reconcileWallet(walletId: string): Promise<ReconciliationResult> {
  return api<ReconciliationResult>('/api/reconcile', {
    method: 'POST',
    body: JSON.stringify({ walletId }),
  });
}

export async function fetchAccount(walletId?: string): Promise<Account> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  return api<Account>(`/api/portfolio${qs}`);
}

export async function fetchPortfolioHistory(walletId?: string, limit = 100): Promise<PortfolioHistoryPoint[]> {
  const qs = new URLSearchParams();
  if (walletId) qs.set('wallet_id', walletId);
  qs.set('limit', String(limit));
  return api<PortfolioHistoryPoint[]>(`/api/portfolio/history?${qs.toString()}`);
}

export interface ExecuteInput {
  signalId: string;
  walletId: string;
  mode?: 'paper' | 'live';
  masterPassword?: string;
  orderType?: 'market' | 'limit';
  limitPrice?: number;
  tif?: 'Alo' | 'Gtc' | 'Ioc';
  expireMinutes?: number;
}

export async function executeSignal(input: ExecuteInput): Promise<{ order: Order; position: Position | null }> {
  return api<{ order: Order; position: Position | null }>('/api/execute', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export interface OrderBook {
  bid?: { avgPrice?: number | string; top?: Array<{ price?: number | string }> };
  ask?: { avgPrice?: number | string; top?: Array<{ price?: number | string }> };
}

export async function fetchOrderbook(symbol: string): Promise<OrderBook> {
  return api<OrderBook>(`/api/orderbook/${encodeURIComponent(symbol)}`);
}

export interface ClosePositionInput {
  positionId: string;
  walletId: string;
  mode?: 'paper' | 'live';
  masterPassword?: string;
}

export async function closePosition(input: ClosePositionInput): Promise<{ position: Position; netPnl: number }> {
  return api<{ position: Position; netPnl: number }>(`/api/positions/${input.positionId}/close`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function runAnalysis(symbol: string, strategyId?: string, useLlm?: boolean): Promise<Signal> {
  return api<Signal>('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({ symbol, strategyId, useLlm }),
  });
}

export async function fetchModelCatalog(): Promise<ModelCatalog> {
  return api<ModelCatalog>('/api/models');
}

export async function fetchStrategies(): Promise<Strategy[]> {
  return api<Strategy[]>('/api/strategies');
}

export async function fetchStrategy(id: string): Promise<Strategy> {
  return api<Strategy>(`/api/strategies/${id}`);
}

export async function createStrategy(strategy: StrategyInput): Promise<Strategy> {
  return api<Strategy>('/api/strategies', {
    method: 'POST',
    body: JSON.stringify(strategy),
  });
}

export async function updateStrategy(id: string, strategy: StrategyInput): Promise<Strategy> {
  return api<Strategy>(`/api/strategies/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(strategy),
  });
}

export async function deleteStrategy(id: string): Promise<void> {
  await api<{ deleted: boolean }>(`/api/strategies/${id}`, { method: 'DELETE' });
}

export async function runBacktest(input: BacktestInput): Promise<BacktestResult> {
  return api<BacktestResult>('/api/backtest', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function startStrategySearch(input: StrategySearchInput): Promise<StrategySearchJob> {
  return api<StrategySearchJob>('/api/strategy-search', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function fetchStrategySearch(searchId: string): Promise<StrategySearchJob> {
  return api<StrategySearchJob>(`/api/strategy-search/${encodeURIComponent(searchId)}`);
}

export interface UserFees {
  address: string;
  userCrossRate: number;
  userAddRate: number;
  userSpotCrossRate: number;
  userSpotAddRate: number;
  makerFee: number;
  takerFee: number;
  spotMakerFee: number;
  spotTakerFee: number;
  activeReferralDiscount: unknown;
  activeStakingDiscount: unknown;
  feeSchedule: unknown;
}

export async function fetchUserFees(address: string): Promise<UserFees> {
  return api<UserFees>(`/api/fees/${encodeURIComponent(address)}`);
}

export interface SlippageEstimate {
  symbol: string;
  notional: number;
  slippagePct: number;
  slippageBps: number;
  source: 'live_book';
}

export async function fetchSlippageEstimate(
  symbol: string,
  notional: number,
): Promise<SlippageEstimate> {
  return api<SlippageEstimate>(
    `/api/slippage-estimate/${encodeURIComponent(symbol)}?notional=${encodeURIComponent(notional)}`,
  );
}

export interface SignalCreateInput {
  symbol: string;
  strategyId?: string;
  strategy?: Record<string, unknown>;
  useLlm?: boolean;
}

export async function createSignal(input: SignalCreateInput): Promise<Signal> {
  return api<Signal>('/api/signals', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function acceptSignal(id: string): Promise<void> {
  await api<{ ok: boolean }>(`/api/signals/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'accepted' }),
  });
}

export async function rejectSignal(id: string): Promise<void> {
  await api<{ ok: boolean }>(`/api/signals/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'rejected' }),
  });
}

export async function deleteSignal(id: string): Promise<void> {
  await api<{ deleted: boolean }>(`/api/signals/${id}`, { method: 'DELETE' });
}

export async function fetchWallets(): Promise<Wallet[]> {
  return api<Wallet[]>('/api/wallets');
}

export async function fetchWallet(id: string): Promise<Wallet> {
  return api<Wallet>(`/api/wallets/${id}`);
}

export async function fetchDefaultWallet(): Promise<Wallet> {
  return api<Wallet>('/api/wallets/default');
}

export async function createWallet(wallet: WalletInput): Promise<Wallet> {
  return api<Wallet>('/api/wallets', {
    method: 'POST',
    body: JSON.stringify(wallet),
  });
}

export async function updateWallet(id: string, wallet: WalletUpdateInput): Promise<Wallet> {
  return api<Wallet>(`/api/wallets/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(wallet),
  });
}

export async function deleteWallet(id: string): Promise<void> {
  await api<{ deleted: boolean }>(`/api/wallets/${id}`, { method: 'DELETE' });
}

export async function fetchAlerts(walletId?: string, unreadOnly = false): Promise<Alert[]> {
  const qs = new URLSearchParams();
  if (walletId) qs.set('wallet_id', walletId);
  if (unreadOnly) qs.set('unread_only', 'true');
  return api<Alert[]>(`/api/alerts?${qs.toString()}`);
}

export async function fetchUnreadAlertCount(walletId?: string): Promise<number> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  const res = await api<{ unread: number }>(`/api/alerts/unread${qs}`);
  return res.unread;
}

export async function markAlertRead(alertId: string): Promise<void> {
  await api<{ read: boolean }>(`/api/alerts/${alertId}/read`, { method: 'POST' });
}

export async function markAllAlertsRead(walletId?: string): Promise<void> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  await api<{ read: boolean }>(`/api/alerts/read-all${qs}`, { method: 'POST' });
}

export async function fetchJournal(walletId?: string, limit = 100): Promise<JournalEntry[]> {
  const qs = new URLSearchParams();
  if (walletId) qs.set('wallet_id', walletId);
  qs.set('limit', String(limit));
  return api<JournalEntry[]>(`/api/journal?${qs.toString()}`);
}
