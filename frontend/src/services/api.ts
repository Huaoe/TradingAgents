import type { Market, Signal, Position, Order, Account } from '../types';
import { markets as mockMarkets, signals as mockSignals, positions as mockPositions, orders as mockOrders, account as mockAccount } from '../data/mockData';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function fetchMarkets(): Promise<Market[]> {
  await delay(400);
  return mockMarkets;
}

export async function fetchSignals(): Promise<Signal[]> {
  await delay(300);
  return mockSignals;
}

export async function fetchPositions(): Promise<Position[]> {
  await delay(300);
  return mockPositions;
}

export async function fetchOrders(): Promise<Order[]> {
  await delay(300);
  return mockOrders;
}

export async function fetchAccount(): Promise<Account> {
  await delay(200);
  return mockAccount;
}

export async function runAnalysis(symbol: string): Promise<Signal> {
  await delay(1500);
  const market = mockMarkets.find((m) => m.symbol === symbol);
  if (!market) throw new Error('Market not found');
  return {
    id: `sig-${Date.now()}`,
    symbol,
    action: market.signal || 'HOLD',
    confidence: market.confidence || 50,
    size: 500,
    entry: market.price,
    stop: market.price * 0.95,
    target: market.price * 1.08,
    leverage: 3,
    reasoning: `Agents analyzed ${symbol}. ${market.name} showed a ${market.signal?.toLowerCase() || 'hold'} setup with ${market.confidence}% confidence.`,
    agents: ['Market', 'Funding', 'Risk'],
    timestamp: new Date().toISOString(),
    status: 'pending',
  };
}

export async function acceptSignal(id: string): Promise<void> {
  await delay(300);
  console.log('Signal accepted:', id);
}

export async function rejectSignal(id: string): Promise<void> {
  await delay(300);
  console.log('Signal rejected:', id);
}
