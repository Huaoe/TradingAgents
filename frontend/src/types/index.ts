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
}

export type PositionSide = 'LONG' | 'SHORT';

export interface Position {
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
  wallet: string;
  totalValue: number;
  available: number;
  marginUsed: number;
  unrealizedPnl: number;
  dailyPnl: number;
}

export type ExecutionMode = 'manual' | 'auto-confirm' | 'auto';
export type LLMMode = 'quick' | 'deep';

export interface RiskConfig {
  longFundingThreshold: number;
  shortFundingThreshold: number;
  leverage: number;
  allocation: number;
  confidenceFloor: number;
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
  name: string;
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
