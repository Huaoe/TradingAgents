import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Trash2, Bot, ChevronRight } from 'lucide-react';
import { fetchStrategies, deleteStrategy } from '../services/api';
import type { Strategy } from '../types';

const TEMPLATE_CARDS: { template: string; title: string; description: string }[] = [
  { template: 'momentum_breakout', title: 'Momentum Breakout', description: 'Volume-confirmed breakouts, rising OI, trailing stop.' },
  { template: 'mean_reversion', title: 'Mean Reversion', description: 'RSI/MACD extremes and liquidation wicks.' },
  { template: 'funding_rate_arb', title: 'Funding Rate Arb', description: 'Fade funding extremes vs. spot.' },
  { template: 'hype_delta_neutral', title: 'HYPE Delta Neutral', description: 'Harvest funding while keeping delta near zero.' },
  { template: 'trend_following', title: 'Trend Following', description: 'SMA/EMA aligned trends with momentum confirmation.' },
  { template: 'scalp_momentum', title: 'Scalp Momentum', description: 'Short-term 5-15m burst plays with tight stops.' },
  { template: 'news_event', title: 'News Event', description: 'React to catalysts with News and Sentiment agents.' },
  { template: 'basis_arbitrage', title: 'Basis Arbitrage', description: 'Trade spot vs perpetual convergence.' },
  { template: 'grid_trading', title: 'Grid Trading', description: 'Buy near range lows, sell/short near range highs in sideways markets.' },
  { template: 'dual_thrust', title: 'Dual Thrust', description: 'Classic range-breakout bands built from recent high/low/close spread.' },
  { template: 'turtle_breakout', title: 'Turtle Breakout', description: 'Donchian-channel breakout in the spirit of the Turtle Trading system.' },
  { template: 'ema_bands_trend_catch', title: 'EMA Bands Trend Catch', description: 'EMA high/low band breakouts with Bollinger/RSI exhaustion counter-trend signals.' },
  { template: 'atr_rsi_combo', title: 'ATR-RSI Combo', description: 'Volatility expansion plus RSI extremes: ATR above its 20 SMA and RSI < 30 or > 70.' },
  { template: 'time_series_momentum', title: 'Time Series Momentum', description: 'Long/short based on the sign of the trailing N-bar return (Moskowitz/Ooi/Pedersen effect).' },
  { template: 'overnight_seasonality_btc', title: 'Overnight Seasonality (BTC)', description: 'Long-only intraday seasonality window: 22:00-23:59 UTC.' },
  { template: 'custom', title: 'Custom', description: 'Build your own strategy from scratch.' },
];

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStrategies();
  }, []);

  const loadStrategies = async () => {
    setLoading(true);
    try {
      const data = await fetchStrategies();
      setStrategies(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this strategy?')) return;
    try {
      await deleteStrategy(id);
      setStrategies((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      console.error(err);
      alert('Failed to delete strategy');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Strategies</h1>
          <p className="text-gray-400 text-sm">Create and manage trading bot strategies.</p>
        </div>
        <Link
          to="/strategies/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> New Strategy
        </Link>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-3">Templates</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {TEMPLATE_CARDS.map((t) => (
            <Link
              key={t.template}
              to={`/strategies/new?template=${t.template}`}
              className="p-4 rounded-xl border border-gray-800 bg-[#11141c] hover:border-violet-500/40 transition-colors group"
            >
              <div className="flex items-center gap-2 text-violet-300 mb-2">
                <Bot className="w-4 h-4" />
                <span className="font-medium">{t.title}</span>
              </div>
              <p className="text-sm text-gray-400">{t.description}</p>
              <div className="mt-4 flex items-center text-xs text-violet-400 group-hover:text-violet-300">
                Use template <ChevronRight className="w-3 h-3 ml-1" />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Saved Strategies</h2>
        {loading ? (
          <p className="text-gray-500 text-sm">Loading...</p>
        ) : strategies.length === 0 ? (
          <p className="text-gray-500 text-sm">No saved strategies yet. Pick a template to get started.</p>
        ) : (
          <div className="space-y-2">
            {strategies.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between p-4 rounded-xl border border-gray-800 bg-[#11141c] hover:border-gray-700"
              >
                <div>
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs text-gray-400 mt-1">
                    {s.template} • {s.executionMode} • {s.markets.length || 'All'} markets • {s.llmProvider}/{s.llmModel}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    to={`/strategies/${s.id}`}
                    className="px-3 py-1.5 text-sm rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors"
                  >
                    Edit
                  </Link>
                  <button
                    onClick={() => handleDelete(s.id)}
                    className="p-1.5 text-gray-400 hover:text-red-400 transition-colors"
                    aria-label="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
