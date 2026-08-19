export type SignalAction = 'BUY' | 'SELL' | 'HOLD';
export type MarketType = 'perp' | 'spot';

export interface Market {
  symbol: string;
  name: string;
  type: MarketType;
  price: number;
  change24h: number;
  volume24h: number;
  funding?: number;
  openInterest?: number;
  maxLeverage?: number;
  signal?: SignalAction;
  confidence?: number;
}

export interface Signal {
  id: string;
  symbol: string;
  action: SignalAction;
  confidence: number;
  size: number;
  entry: number;
  stop: number;
  target: number;
  leverage?: number;
  reasoning: string;
  agents: string[];
  timestamp: string;
  status: 'pending' | 'accepted' | 'rejected';
  meta?: Record<string, any>;
}

export type PositionSide = 'LONG' | 'SHORT';

export interface Position {
  id: string;
  orderId: string;
  walletId: string;
  symbol: string;
  side: PositionSide;
  size: number;
  entryPrice: number;
  markPrice: number;
  pnl: number;
  pnlPct: number;
  liquidationPrice?: number;
  margin: number;
  leverage: number;
  status: string;
  openedAt: string;
  closedAt: string | null;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  size: number;
  price: number;
  type: 'Market' | 'Limit';
  status: 'filled' | 'open' | 'cancelled';
  timestamp: string;
}

export interface Account {
  walletId?: string;
  wallet?: string;
  mode?: string;
  balance: number;
  totalValue: number;
  available: number;
  marginUsed: number;
  unrealizedPnl: number;
  dailyPnl: number;
  totalNotional?: number;
  openPositions?: number;
  maxExposureSymbol?: string;
  maxExposureNotional?: number;
  maxLeverage?: number;
  llmSpend?: number;
  llmTokensIn?: number;
  llmTokensOut?: number;
  llmCalls?: number;
}

export interface PortfolioHistoryPoint {
  timestamp: string;
  totalValue: number;
}

export type ExecutionMode = 'manual' | 'auto-confirm' | 'auto';
export type LLMMode = 'quick' | 'deep';

export interface RiskConfig {
  longFundingThreshold: number;
  shortFundingThreshold: number;
  fundingExtremeK?: number;
  leverage: number;
  allocation: number;
  confidenceFloor: number;
  minHoldBars?: number;
  cooldownBars?: number;
  exitHysteresis?: number;
  stopLossPct?: number;
  takeProfitPct?: number;
  trailingStopPct?: number;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  template: string;
  markets: string[];
  agents: string[];
  llmProvider: string;
  llmModel: string;
  llmMode: LLMMode;
  executionMode: ExecutionMode;
  schedule: string;
  riskConfig: RiskConfig;
  createdAt: string;
  updatedAt: string;
}

export interface StrategyInput {
  name?: string;
  description?: string;
  template?: string;
  markets?: string[];
  agents?: string[];
  llmProvider?: string;
  llmModel?: string;
  llmMode?: LLMMode;
  executionMode?: ExecutionMode;
  schedule?: string;
  riskConfig?: Partial<RiskConfig>;
}

export interface ModelCatalog {
  [provider: string]: {
    [mode: string]: { label: string; value: string }[];
  };
}

export type BacktestInterval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d';

export interface BacktestSummary {
  initialBalance: number;
  finalBalance: number;
  totalReturnPct: number;
  benchmarkReturnPct: number;
  sharpeRatio: number;
  maxDrawdownPct: number;
  winRatePct: number;
  profitFactor: number;
  totalTrades: number;
  avgTradeReturnPct: number;
  avgWinPct: number;
  avgLossPct: number;
  avgConfidence?: number;
  avgSignalConfidence?: number;
  confidenceFloor: number;
  leverage: number;
  allocation: number;
  finalSignal: number;
  longSignals: number;
  shortSignals: number;
  flatSignals: number;
  startTime: string;
  endTime: string;
  interval: string;
  symbol: string;
  strategyName: string;
  makerFee: number;
  takerFee: number;
  slippagePct: number;
  orderType: 'maker' | 'taker';
  totalGrossPnl: number;
  totalFees: number;
  totalFundingCost: number;
  grossProfitFactor: number;
  totalNetPnl: number;
}

export interface BacktestTrade {
  entryTime: string;
  exitTime: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  sizeCoin: number;
  notional: number;
  leverage: number;
  grossPnl: number;
  fees: number;
  fundingCost: number;
  netPnl: number;
  returnPct: number;
  confidence: number;
  exitReason: 'signal' | 'stop_loss' | 'take_profit' | 'trailing_stop' | 'end_of_backtest';
}

export interface BacktestResult {
  summary: BacktestSummary;
  equity: { time: string; equity: number }[];
  drawdown: { time: string; drawdown: number }[];
  price: { time: string; close: number }[];
  trades: BacktestTrade[];
  monthlyReturns: Record<string, number> | null;
}

export interface BacktestInput {
  symbol: string;
  interval: BacktestInterval;
  startAt: string;
  endAt: string;
  strategyId?: string;
  strategy?: Record<string, unknown>;
  initialBalance?: number;
  makerFee?: number;
  takerFee?: number;
  slippagePct?: number;
  orderType?: 'maker' | 'taker';
}

export interface Wallet {
  id: string;
  name: string;
  address: string;
  chain: string;
  isDefault: boolean;
  encryptedKey: string;
  createdAt: string;
  updatedAt: string;
}

export interface WalletInput {
  name: string;
  address: string;
  chain?: string;
  isDefault?: boolean;
  privateKey: string;
  masterPassword: string;
}

export interface WalletUpdateInput {
  name?: string;
  isDefault?: boolean;
}

export interface Alert {
  id: string;
  walletId?: string;
  relatedId?: string;
  type: 'signal' | 'position' | 'risk' | 'system';
  severity: 'info' | 'success' | 'warning' | 'error';
  message: string;
  read: boolean;
  timestamp: string;
}

export interface JournalEntry {
  id: string;
  walletId?: string;
  positionId?: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  size: number;
  leverage: number;
  grossPnl: number;
  fees: number;
  netPnl: number;
  reasoning?: string;
  reflection?: string;
  openedAt: string;
  closedAt: string;
}
