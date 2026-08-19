import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Save, AlertTriangle, Loader2 } from 'lucide-react';
import { createStrategy, updateStrategy, fetchStrategy, fetchMarkets, fetchModelCatalog } from '../services/api';
import type { Market, Strategy, StrategyInput, ModelCatalog } from '../types';

const ALL_AGENTS = ['Market', 'Funding', 'OrderBook', 'Sentiment', 'News'];

const DEFAULT_STRATEGY: StrategyInput = {
  name: '',
  description: '',
  template: 'custom',
  markets: [],
  agents: ['Market', 'Funding', 'OrderBook'],
  llmProvider: 'glm',
  llmModel: 'glm-5-turbo',
  llmMode: 'quick',
  executionMode: 'manual',
  schedule: '',
  riskConfig: {
    longFundingThreshold: -0.0005,
    shortFundingThreshold: 0.0012,
    leverage: 3,
    allocation: 10,
    confidenceFloor: 60,
    minHoldBars: 3,
    cooldownBars: 3,
    exitHysteresis: 50,
    stopLossPct: 2,
    takeProfitPct: 4,
    trailingStopPct: 1.5,
  },
};

const TEMPLATE_DEFAULTS: Record<string, Partial<StrategyInput>> = {
  momentum_breakout: { agents: ['Market', 'Sentiment', 'News'], riskConfig: { leverage: 5, allocation: 15, confidenceFloor: 65 } },
  mean_reversion: { agents: ['Market', 'Sentiment'], riskConfig: { leverage: 3, allocation: 10, confidenceFloor: 60 } },
  funding_rate_arb: { agents: ['Market', 'Funding'], riskConfig: { leverage: 2, allocation: 20, confidenceFloor: 70 } },
  hype_delta_neutral: { agents: ['Market', 'Funding'], riskConfig: { leverage: 1, allocation: 25, confidenceFloor: 75 } },
  trend_following: { agents: ['Market', 'OrderBook'], riskConfig: { leverage: 4, allocation: 12, confidenceFloor: 62 } },
  scalp_momentum: { agents: ['Market', 'OrderBook'], riskConfig: { leverage: 6, allocation: 8, confidenceFloor: 68 } },
  news_event: { agents: ['News', 'Sentiment', 'Market'], riskConfig: { leverage: 4, allocation: 10, confidenceFloor: 70 } },
  basis_arbitrage: { agents: ['Market', 'Funding'], riskConfig: { leverage: 2, allocation: 30, confidenceFloor: 75 } },
  grid_trading: { agents: ['Market', 'OrderBook'], riskConfig: { leverage: 2, allocation: 10, confidenceFloor: 60 } },
  dual_thrust: { agents: ['Market', 'OrderBook'], riskConfig: { leverage: 3, allocation: 12, confidenceFloor: 60 } },
  turtle_breakout: { agents: ['Market', 'Funding'], riskConfig: { leverage: 3, allocation: 12, confidenceFloor: 60 } },
  ema_bands_trend_catch: { agents: ['Market', 'OrderBook'], riskConfig: { leverage: 3, allocation: 12, confidenceFloor: 60 } },
  atr_rsi_combo: { agents: ['Market', 'Sentiment'], riskConfig: { leverage: 3, allocation: 10, confidenceFloor: 60 } },
  time_series_momentum: { agents: ['Market', 'Funding'], riskConfig: { leverage: 3, allocation: 12, confidenceFloor: 60 } },
  overnight_seasonality_btc: { agents: ['Market'], riskConfig: { leverage: 2, allocation: 10, confidenceFloor: 65 } },
  custom: { agents: ['Market', 'Funding', 'OrderBook'], riskConfig: { leverage: 3, allocation: 10, confidenceFloor: 60 } },
};

function PercentInput({
  value,
  onChange,
  min,
  max,
  step,
  placeholder,
}: {
  value: number | undefined;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number | string;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
        className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none pr-8"
      />
      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">%</span>
    </div>
  );
}

export function StrategyEditor() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isNew = !id;
  const templateKey = searchParams.get('template') || 'custom';

  const templateDefaults = TEMPLATE_DEFAULTS[templateKey] || {};
  const [strategy, setStrategy] = useState<StrategyInput>({
    ...DEFAULT_STRATEGY,
    ...templateDefaults,
    template: templateKey,
    riskConfig: {
      ...DEFAULT_STRATEGY.riskConfig,
      ...templateDefaults.riskConfig,
    },
  });
  const [markets, setMarkets] = useState<Market[]>([]);
  const [catalog, setCatalog] = useState<ModelCatalog>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchMarkets().then((m) => setMarkets(m.filter((x) => x.type === 'perp').sort((a, b) => b.volume24h - a.volume24h))).catch(() => setMarkets([]));
    fetchModelCatalog().then(setCatalog).catch(() => setCatalog({}));
  }, []);

  useEffect(() => {
    if (isNew) return;
    fetchStrategy(id)
      .then((s: Strategy) => {
        setStrategy({
          name: s.name,
          description: s.description,
          template: s.template,
          markets: s.markets,
          agents: s.agents,
          llmProvider: s.llmProvider,
          llmModel: s.llmModel,
          llmMode: s.llmMode,
          executionMode: s.executionMode,
          schedule: s.schedule,
          riskConfig: {
            longFundingThreshold: (s.riskConfig.longFundingThreshold * 100),
            shortFundingThreshold: (s.riskConfig.shortFundingThreshold * 100),
            leverage: s.riskConfig.leverage,
            allocation: s.riskConfig.allocation * 100,
            confidenceFloor: s.riskConfig.confidenceFloor,
            minHoldBars: s.riskConfig.minHoldBars,
            cooldownBars: s.riskConfig.cooldownBars,
            exitHysteresis: s.riskConfig.exitHysteresis,
            stopLossPct: s.riskConfig.stopLossPct != null ? s.riskConfig.stopLossPct * 100 : undefined,
            takeProfitPct: s.riskConfig.takeProfitPct != null ? s.riskConfig.takeProfitPct * 100 : undefined,
            trailingStopPct: s.riskConfig.trailingStopPct != null ? s.riskConfig.trailingStopPct * 100 : undefined,
          },
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load strategy'))
      .finally(() => setLoading(false));
  }, [id, isNew]);

  const providers = useMemo(() => Object.keys(catalog), [catalog]);
  const modes = useMemo(() => {
    if (!strategy.llmProvider || !catalog[strategy.llmProvider]) return [];
    return Object.keys(catalog[strategy.llmProvider]);
  }, [catalog, strategy.llmProvider]);
  const modelOptions = useMemo(() => {
    if (!strategy.llmProvider || !catalog[strategy.llmProvider] || !strategy.llmMode) return [];
    return catalog[strategy.llmProvider][strategy.llmMode] || [];
  }, [catalog, strategy.llmProvider, strategy.llmMode]);

  const updateField = <K extends keyof StrategyInput>(field: K, value: StrategyInput[K]) => {
    setStrategy((prev) => ({ ...prev, [field]: value }));
  };

  const updateRisk = (field: keyof NonNullable<StrategyInput['riskConfig']>, value: number) => {
    setStrategy((prev) => ({ ...prev, riskConfig: { ...prev.riskConfig, [field]: value } }));
  };

  const toggleMarket = (symbol: string) => {
    const current = strategy.markets || [];
    if (current.includes(symbol)) {
      updateField('markets', current.filter((s) => s !== symbol));
    } else {
      updateField('markets', [...current, symbol]);
    }
  };

  const toggleAgent = (agent: string) => {
    const current = strategy.agents || [];
    if (current.includes(agent)) {
      updateField('agents', current.filter((a) => a !== agent));
    } else {
      updateField('agents', [...current, agent]);
    }
  };

  const validate = (): boolean => {
    if (!strategy.name?.trim()) {
      setError('Strategy name is required.');
      return false;
    }
    if (!strategy.llmProvider || !strategy.llmMode) {
      setError('LLM provider and mode are required.');
      return false;
    }
    if (!strategy.llmModel) {
      setError('An LLM model must be selected.');
      return false;
    }
    if (modelOptions.length > 0 && !modelOptions.some((m) => m.value === strategy.llmModel)) {
      setError('The selected LLM model is not available for the chosen provider and mode.');
      return false;
    }
    if (!strategy.agents || strategy.agents.length === 0) {
      setError('Select at least one agent.');
      return false;
    }
    const rc = strategy.riskConfig;
    if (!rc) {
      setError('Risk configuration is missing.');
      return false;
    }
    if ((rc.allocation ?? 0) < 0 || (rc.allocation ?? 0) > 100) {
      setError('Trade allocation must be between 0% and 100%.');
      return false;
    }
    if ((rc.confidenceFloor ?? 0) < 0 || (rc.confidenceFloor ?? 0) > 100) {
      setError('Confidence floor must be between 0% and 100%.');
      return false;
    }
    if ((rc.leverage ?? 0) < 1) {
      setError('Max leverage must be at least 1x.');
      return false;
    }
    if ((rc.longFundingThreshold ?? 0) < -100 || (rc.longFundingThreshold ?? 0) > 100) {
      setError('Funding thresholds must be between -100% and 100%.');
      return false;
    }
    if ((rc.shortFundingThreshold ?? 0) < -100 || (rc.shortFundingThreshold ?? 0) > 100) {
      setError('Funding thresholds must be between -100% and 100%.');
      return false;
    }
    if ((rc.minHoldBars ?? 0) < 0 || (rc.cooldownBars ?? 0) < 0) {
      setError('Hold and cooldown bars cannot be negative.');
      return false;
    }
    if ((rc.exitHysteresis ?? 50) < 0 || (rc.exitHysteresis ?? 50) > 100) {
      setError('Exit hysteresis must be between 0 and 100.');
      return false;
    }
    if ((rc.stopLossPct ?? 0) < 0 || (rc.takeProfitPct ?? 0) < 0 || (rc.trailingStopPct ?? 0) < 0) {
      setError('Stop, target, and trailing percentages cannot be negative.');
      return false;
    }
    setError('');
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const payload: StrategyInput = {
        ...strategy,
        riskConfig: {
          longFundingThreshold: (strategy.riskConfig?.longFundingThreshold || 0) / 100,
          shortFundingThreshold: (strategy.riskConfig?.shortFundingThreshold || 0) / 100,
          leverage: strategy.riskConfig?.leverage || 3,
          allocation: (strategy.riskConfig?.allocation || 10) / 100,
          confidenceFloor: strategy.riskConfig?.confidenceFloor || 60,
          minHoldBars: strategy.riskConfig?.minHoldBars,
          cooldownBars: strategy.riskConfig?.cooldownBars,
          exitHysteresis: strategy.riskConfig?.exitHysteresis,
          stopLossPct: strategy.riskConfig?.stopLossPct != null ? strategy.riskConfig.stopLossPct / 100 : undefined,
          takeProfitPct: strategy.riskConfig?.takeProfitPct != null ? strategy.riskConfig.takeProfitPct / 100 : undefined,
          trailingStopPct: strategy.riskConfig?.trailingStopPct != null ? strategy.riskConfig.trailingStopPct / 100 : undefined,
        },
      };
      if (isNew) {
        await createStrategy(payload);
      } else {
        await updateStrategy(id, payload);
      }
      navigate('/strategies');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save strategy');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/strategies" className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">{isNew ? 'New Strategy' : 'Edit Strategy'}</h1>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <div className="flex-1">{error}</div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 max-w-4xl">
        <section className="p-4 rounded-xl border border-gray-800 bg-[#11141c] space-y-4">
          <h2 className="font-semibold text-violet-300">General</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Name *</label>
              <input
                type="text"
                value={strategy.name}
                onChange={(e) => updateField('name', e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Template</label>
              <input
                type="text"
                value={strategy.template}
                disabled
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 text-gray-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <textarea
              value={strategy.description}
              onChange={(e) => updateField('description', e.target.value)}
              rows={2}
              className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
            />
          </div>
        </section>

        <section className="p-4 rounded-xl border border-gray-800 bg-[#11141c] space-y-4">
          <h2 className="font-semibold text-violet-300">Agents & Model</h2>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Active agents *</label>
            <div className="flex flex-wrap gap-2">
              {ALL_AGENTS.map((agent) => (
                <button
                  key={agent}
                  type="button"
                  onClick={() => toggleAgent(agent)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    strategy.agents?.includes(agent)
                      ? 'bg-violet-600/20 border-violet-500/40 text-violet-200'
                      : 'bg-[#0b0d12] border-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  {agent}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Provider *</label>
              <select
                value={strategy.llmProvider}
                onChange={(e) => updateField('llmProvider', e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              >
                {providers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Mode *</label>
              <select
                value={strategy.llmMode}
                onChange={(e) => updateField('llmMode', e.target.value as 'quick' | 'deep')}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              >
                {modes.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Model *</label>
              <select
                value={strategy.llmModel}
                onChange={(e) => updateField('llmModel', e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              >
                {modelOptions.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        <section className="p-4 rounded-xl border border-gray-800 bg-[#11141c] space-y-4">
          <h2 className="font-semibold text-violet-300">Markets</h2>
          <div className="max-h-64 overflow-auto border border-gray-800 rounded-lg p-2 bg-[#0b0d12]">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {markets.slice(0, 100).map((m) => (
                <label key={m.symbol} className="flex items-center gap-2 text-sm text-gray-300 hover:bg-gray-800/50 p-1.5 rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={strategy.markets?.includes(m.symbol)}
                    onChange={() => toggleMarket(m.symbol)}
                    className="accent-violet-500"
                  />
                  <span className="truncate">{m.symbol}</span>
                </label>
              ))}
            </div>
          </div>
        </section>

        <section className="p-4 rounded-xl border border-gray-800 bg-[#11141c] space-y-4">
          <h2 className="font-semibold text-violet-300">Risk & Execution</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Max leverage</label>
              <input
                type="number"
                min={1}
                value={strategy.riskConfig?.leverage}
                onChange={(e) => updateRisk('leverage', parseInt(e.target.value, 10))}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Trade allocation (%)</label>
              <PercentInput
                min={0}
                max={100}
                value={strategy.riskConfig?.allocation}
                onChange={(value) => updateRisk('allocation', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Confidence floor (%)</label>
              <PercentInput
                min={0}
                max={100}
                step={1}
                value={strategy.riskConfig?.confidenceFloor}
                onChange={(value) => updateRisk('confidenceFloor', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Long funding threshold (hourly %)</label>
              <PercentInput
                step={0.0001}
                value={strategy.riskConfig?.longFundingThreshold}
                onChange={(value) => updateRisk('longFundingThreshold', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Short funding threshold (hourly %)</label>
              <PercentInput
                step={0.0001}
                value={strategy.riskConfig?.shortFundingThreshold}
                onChange={(value) => updateRisk('shortFundingThreshold', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Minimum hold (bars)</label>
              <input
                type="number"
                min={0}
                value={strategy.riskConfig?.minHoldBars ?? ''}
                onChange={(e) => updateRisk('minHoldBars', e.target.value === '' ? 0 : parseInt(e.target.value, 10))}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Post-exit cooldown (bars)</label>
              <input
                type="number"
                min={0}
                value={strategy.riskConfig?.cooldownBars ?? ''}
                onChange={(e) => updateRisk('cooldownBars', e.target.value === '' ? 0 : parseInt(e.target.value, 10))}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Exit hysteresis score</label>
              <input
                type="number"
                min={0}
                max={100}
                value={strategy.riskConfig?.exitHysteresis ?? ''}
                onChange={(e) => updateRisk('exitHysteresis', e.target.value === '' ? 0 : Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Stop loss (%)</label>
              <PercentInput
                min={0}
                step={0.1}
                value={strategy.riskConfig?.stopLossPct}
                onChange={(value) => updateRisk('stopLossPct', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Take profit (%)</label>
              <PercentInput
                min={0}
                step={0.1}
                value={strategy.riskConfig?.takeProfitPct}
                onChange={(value) => updateRisk('takeProfitPct', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Trailing stop (%)</label>
              <PercentInput
                min={0}
                step={0.1}
                value={strategy.riskConfig?.trailingStopPct}
                onChange={(value) => updateRisk('trailingStopPct', value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Execution mode</label>
              <select
                value={strategy.executionMode}
                onChange={(e) => updateField('executionMode', e.target.value as 'manual' | 'auto-confirm' | 'auto')}
                className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
              >
                <option value="manual">Manual</option>
                <option value="auto-confirm">Auto-confirm</option>
                <option value="auto">Auto</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Schedule (cron or human readable)</label>
            <input
              type="text"
              value={strategy.schedule}
              onChange={(e) => updateField('schedule', e.target.value)}
              placeholder="e.g. every 4 hours"
              className="w-full px-3 py-2 rounded-lg bg-[#0b0d12] border border-gray-800 focus:border-violet-500 outline-none"
            />
          </div>
        </section>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
          >
            <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Strategy'}
          </button>
          <Link
            to="/strategies"
            className="px-5 py-2.5 rounded-lg text-sm font-medium border border-gray-800 hover:bg-gray-800/50 transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
