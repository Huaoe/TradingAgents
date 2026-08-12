import type { Market, Signal, Position, Order, Account, Strategy, StrategyInput, ModelCatalog, BacktestInput, BacktestResult, Wallet, WalletInput, WalletUpdateInput } from '../types';
import { positions as mockPositions, orders as mockOrders, account as mockAccount } from '../data/mockData';

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

export async function fetchPositions(): Promise<Position[]> {
  return mockPositions;
}

export async function fetchOrders(): Promise<Order[]> {
  return mockOrders;
}

export async function fetchAccount(): Promise<Account> {
  return mockAccount;
}

export async function runAnalysis(symbol: string, strategyId?: string, strategy?: Record<string, unknown>): Promise<Signal> {
  return api<Signal>('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({ symbol, strategyId, strategy }),
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
