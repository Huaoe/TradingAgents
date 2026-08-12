import type { Market, Signal, Position, Order, Account } from '../types';
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
  // Signals are generated on demand via /api/analyze for now.
  return [];
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

export async function runAnalysis(symbol: string, strategy?: Record<string, unknown>): Promise<Signal> {
  return api<Signal>('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({ symbol, strategy }),
  });
}

export async function acceptSignal(id: string): Promise<void> {
  console.log('Signal accepted:', id);
}

export async function rejectSignal(id: string): Promise<void> {
  console.log('Signal rejected:', id);
}
