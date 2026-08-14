import type { Market, Signal, Position, Order, Account, Alert, JournalEntry, Strategy, StrategyInput, ModelCatalog, BacktestInput, BacktestResult, Wallet, WalletInput, WalletUpdateInput } from '../types';
import { account as mockAccount } from '../data/mockData';

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

export async function fetchAccount(walletId?: string): Promise<Account> {
  const qs = walletId ? `?wallet_id=${encodeURIComponent(walletId)}` : '';
  try {
    return await api<Account>(`/api/portfolio${qs}`);
  } catch {
    return mockAccount;
  }
}

export interface ExecuteInput {
  signalId: string;
  walletId: string;
  mode?: 'paper' | 'live';
  masterPassword?: string;
}

export async function executeSignal(input: ExecuteInput): Promise<{ order: Order; position: Position | null }> {
  return api<{ order: Order; position: Position | null }>('/api/execute', {
    method: 'POST',
    body: JSON.stringify(input),
  });
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
