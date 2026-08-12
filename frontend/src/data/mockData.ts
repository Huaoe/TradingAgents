import type { Market, Signal, Account } from '../types';

export const account: Account = {
  wallet: '0x71C...9A2',
  balance: 12450.8,
  totalValue: 12450.8,
  available: 8735.5,
  marginUsed: 3715.3,
  unrealizedPnl: 432.2,
  dailyPnl: 128.5,
};

export const markets: Market[] = [
  { symbol: 'BTC', name: 'Bitcoin', type: 'perp', price: 84720.5, change24h: 2.4, volume24h: 1_240_000_000, funding: 0.0081, signal: 'BUY', confidence: 78 },
  { symbol: 'ETH', name: 'Ethereum', type: 'perp', price: 1620.3, change24h: -1.2, volume24h: 580_000_000, funding: -0.0012, signal: 'HOLD', confidence: 52 },
  { symbol: 'SOL', name: 'Solana', type: 'perp', price: 145.8, change24h: 5.7, volume24h: 310_000_000, funding: 0.0154, signal: 'BUY', confidence: 84 },
  { symbol: 'HYPE', name: 'Hyperliquid', type: 'spot', price: 18.25, change24h: 3.1, volume24h: 42_000_000, signal: 'HOLD', confidence: 61 },
  { symbol: 'PURR', name: 'Purr', type: 'spot', price: 0.034, change24h: -8.4, volume24h: 8_500_000, signal: 'SELL', confidence: 71 },
];

export const signals: Signal[] = [
  {
    id: 'sig-1',
    symbol: 'SOL',
    action: 'BUY',
    confidence: 84,
    size: 1200,
    entry: 145.8,
    stop: 138.5,
    target: 160.2,
    leverage: 4,
    reasoning: 'Funding turning positive, OI rising, breakout above 4h resistance with strong social sentiment.',
    agents: ['Market', 'Funding', 'On-Chain', 'Risk'],
    timestamp: '2026-08-12 12:30 UTC',
    status: 'pending',
  },
  {
    id: 'sig-2',
    symbol: 'BTC',
    action: 'BUY',
    confidence: 78,
    size: 850,
    entry: 84720.5,
    stop: 82000,
    target: 90000,
    leverage: 3,
    reasoning: 'ETF inflows accelerating, technical breakout, funding neutral.',
    agents: ['Market', 'Macro', 'Risk'],
    timestamp: '2026-08-12 12:15 UTC',
    status: 'accepted',
  },
  {
    id: 'sig-3',
    symbol: 'PURR',
    action: 'SELL',
    confidence: 71,
    size: 500,
    entry: 0.034,
    stop: 0.038,
    target: 0.028,
    leverage: 2,
    reasoning: 'Meme fatigue, volume dropping, large holders distributing.',
    agents: ['On-Chain', 'Social', 'Risk'],
    timestamp: '2026-08-12 11:50 UTC',
    status: 'rejected',
  },
];

export const equityData = Array.from({ length: 30 }, (_, i) => ({
  day: `D${i + 1}`,
  value: 10000 + (i * 85) + Math.sin(i) * 200,
}));
