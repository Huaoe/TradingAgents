import { Fragment, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Loader2, AlertCircle, Search, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import { Card, Badge } from '../components/Card';
import { fetchMarkets, fetchStrategies, runAnalysis, fetchAccount } from '../services/api';
import type { Market, Signal, Strategy, Account } from '../types';

export function Scanner() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('');
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [latestSignal, setLatestSignal] = useState<Signal | null>(null);
  const [signals, setSignals] = useState<Record<string, Signal>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const navigate = useNavigate();
  const [useLlm, setUseLlm] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const [backtestSelection, setBacktestSelection] = useState<Record<string, string>>({});

  useEffect(() => {
    fetchMarkets().then(setMarkets);
    fetchStrategies().then(setStrategies).catch(console.error);
    fetchAccount().then(setAccount).catch(() => setAccount(null));
  }, []);

  const handleAnalyze = async (symbol: string) => {
    setError(null);
    setAnalyzing(symbol);
    try {
      const signal = await runAnalysis(symbol, selectedStrategyId || undefined, useLlm);
      setSignals((prev) => ({ ...prev, [symbol]: signal }));
      setLatestSignal(signal);
      setExpanded((prev) => ({ ...prev, [symbol]: true }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Analysis failed';
      setError(`${symbol}: ${message}`);
      console.error(err);
    } finally {
      setAnalyzing(null);
    }
  };

  const toggleExpanded = (symbol: string) => {
    setExpanded((prev) => ({ ...prev, [symbol]: !prev[symbol] }));
  };

  const getSuggestedStrategies = (symbol: string): Strategy[] => {
    const marketStrategies = strategies.filter((s) => s.markets.includes(symbol));
    if (marketStrategies.length) return marketStrategies;
    if (selectedStrategyId) return strategies.filter((s) => s.id === selectedStrategyId).slice(0, 1);
    return strategies.slice(0, 3);
  };

  const filteredMarkets = markets.filter((m) =>
    `${m.symbol} ${m.name}`.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Market Scanner</h1>
          <p className="text-sm text-gray-400 mt-1">Run TradingAgents analysis on Hyperliquid markets</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Filter markets..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-9 pr-3 py-2 rounded-lg bg-[#11141c] border border-gray-800 text-sm focus:border-violet-500 outline-none"
            />
          </div>
          <label className="text-sm text-gray-400">Strategy</label>
          <select
            value={selectedStrategyId}
            onChange={(e) => setSelectedStrategyId(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[#11141c] border border-gray-800 text-sm focus:border-violet-500 outline-none"
          >
            <option value="">Default</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              className="rounded border-gray-700 bg-gray-900 text-violet-600"
            />
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" /> Use LLM
            </span>
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-gray-800 bg-[#11141c]">
          <div className="text-xs text-gray-500 uppercase mb-1">Total LLM Spend</div>
          <div className="text-xl font-semibold">${(account?.llmSpend ?? 0).toFixed(4)}</div>
        </div>
        <div className="p-4 rounded-xl border border-gray-800 bg-[#11141c]">
          <div className="text-xs text-gray-500 uppercase mb-1">Total Tokens</div>
          <div className="text-xl font-semibold">{((account?.llmTokensIn ?? 0) + (account?.llmTokensOut ?? 0)).toLocaleString()}</div>
          <div className="text-xs text-gray-500">{(account?.llmTokensIn ?? 0).toLocaleString()} in / {(account?.llmTokensOut ?? 0).toLocaleString()} out</div>
        </div>
        <div className="p-4 rounded-xl border border-gray-800 bg-[#11141c]">
          <div className="text-xs text-gray-500 uppercase mb-1">LLM Calls</div>
          <div className="text-xl font-semibold">{(account?.llmCalls ?? 0).toLocaleString()}</div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl border border-red-500/30 bg-red-500/5 flex items-start gap-3 text-sm text-red-200">
          <AlertCircle className="w-4 h-4 mt-0.5 text-red-400" />
          {error}
        </div>
      )}

      {latestSignal && (
        <Card className="border-violet-500/30 bg-violet-500/5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Latest Signal: {latestSignal.symbol}</h3>
            <Badge action={latestSignal.action} />
          </div>
          <p className="text-sm text-gray-300 mb-3">{latestSignal.reasoning}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div><span className="text-gray-500">Confidence</span><div>{latestSignal.confidence}%</div></div>
            <div><span className="text-gray-500">Size</span><div>${latestSignal.size}</div></div>
            <div><span className="text-gray-500">Stop</span><div>${latestSignal.stop.toFixed(4)}</div></div>
            <div><span className="text-gray-500">Target</span><div>${latestSignal.target.toFixed(4)}</div></div>
          </div>
          {latestSignal.meta?.llmUsage && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-4 border-t border-gray-800 pt-4">
              <div><span className="text-gray-500">Tokens In</span><div>{latestSignal.meta.llmUsage.tokensIn.toLocaleString()}</div></div>
              <div><span className="text-gray-500">Tokens Out</span><div>{latestSignal.meta.llmUsage.tokensOut.toLocaleString()}</div></div>
              <div><span className="text-gray-500">LLM Calls</span><div>{latestSignal.meta.llmUsage.llmCalls.toLocaleString()}</div></div>
              <div><span className="text-gray-500">Est. Cost</span><div>${latestSignal.meta.llmUsage.spend.toFixed(4)}</div></div>
            </div>
          )}
        </Card>
      )}

      <Card className="overflow-hidden p-0">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800/50 text-gray-400">
            <tr>
              <th className="p-4 font-medium">Market</th>
              <th className="p-4 font-medium">Type</th>
              <th className="p-4 font-medium">Price</th>
              <th className="p-4 font-medium">24h</th>
              <th className="p-4 font-medium">Volume</th>
              <th className="p-4 font-medium">Funding</th>
              <th className="p-4 font-medium">OI</th>
              <th className="p-4 font-medium">Signal</th>
              <th className="p-4 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {filteredMarkets.map((m) => {
              const rowSignal = signals[m.symbol];
              const suggested = rowSignal ? getSuggestedStrategies(m.symbol) : [];
              return (
                <Fragment key={m.symbol}>
                  <tr key={m.symbol} className="hover:bg-gray-800/30 transition-colors">
                    <td className="p-4 font-medium">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleExpanded(m.symbol)}
                          className="p-1 rounded hover:bg-gray-800 text-gray-400"
                          title="Toggle analysis"
                          disabled={!rowSignal}
                        >
                          {expanded[m.symbol] ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                        <span>{m.symbol} <span className="text-gray-500 font-normal">{m.name}</span></span>
                      </div>
                    </td>
                    <td className="p-4 text-gray-400 capitalize">{m.type}</td>
                    <td className="p-4">${m.price.toLocaleString()}</td>
                    <td className={`p-4 ${m.change24h >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{m.change24h >= 0 ? '+' : ''}{m.change24h}%</td>
                    <td className="p-4 text-gray-400">${(m.volume24h / 1e6).toFixed(1)}M</td>
                    <td className="p-4 text-gray-400">{m.funding !== undefined ? `${(m.funding * 100).toFixed(4)}%` : '-'}</td>
                    <td className="p-4 text-gray-400">{m.openInterest !== undefined ? `$${(m.openInterest * (m.price || 0) / 1e6).toFixed(1)}M` : '-'}</td>
                    <td className="p-4">
                      {rowSignal ? (
                        <div className="flex items-center gap-2">
                          <Badge action={rowSignal.action} />
                          <span className="text-xs text-gray-500">{rowSignal.confidence}%</span>
                        </div>
                      ) : m.signal ? (
                        <Badge action={m.signal} />
                      ) : (
                        <span className="text-gray-500">—</span>
                      )}
                    </td>
                    <td className="p-4 text-right">
                      <button
                        onClick={() => handleAnalyze(m.symbol)}
                        disabled={analyzing === m.symbol}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                      >
                        {analyzing === m.symbol ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                        Analyze
                      </button>
                    </td>
                  </tr>

                  {expanded[m.symbol] && rowSignal && (
                    <tr key={`${m.symbol}-analysis`}>
                      <td colSpan={9} className="p-0">
                        <div className="bg-[#0d0f14] border-t border-gray-800 p-4">
                          <h4 className="text-sm font-medium mb-2">Analysis: {m.symbol}</h4>
                          <p className="text-sm text-gray-300 mb-3">{rowSignal.reasoning}</p>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                            <div><span className="text-gray-500">Confidence</span><div>{rowSignal.confidence}%</div></div>
                            <div><span className="text-gray-500">Entry</span><div>${rowSignal.entry.toFixed(4)}</div></div>
                            <div><span className="text-gray-500">Stop</span><div>${rowSignal.stop.toFixed(4)}</div></div>
                            <div><span className="text-gray-500">Target</span><div>${rowSignal.target.toFixed(4)}</div></div>
                          </div>
                          {rowSignal.meta?.llmUsage && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm border-t border-gray-800 pt-4">
                              <div><span className="text-gray-500">Tokens In</span><div>{rowSignal.meta.llmUsage.tokensIn.toLocaleString()}</div></div>
                              <div><span className="text-gray-500">Tokens Out</span><div>{rowSignal.meta.llmUsage.tokensOut.toLocaleString()}</div></div>
                              <div><span className="text-gray-500">LLM Calls</span><div>{rowSignal.meta.llmUsage.llmCalls.toLocaleString()}</div></div>
                              <div><span className="text-gray-500">Est. Cost</span><div>${rowSignal.meta.llmUsage.spend.toFixed(4)}</div></div>
                            </div>
                          )}
                          <div>
                            <h5 className="text-xs font-medium text-gray-400 uppercase mb-2">Suggested Strategies</h5>
                            {suggested.length === 0 ? (
                              <span className="text-sm text-gray-500">No specific strategies for this market.</span>
                            ) : (
                              <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
                                <select
                                  value={backtestSelection[m.symbol] || ''}
                                  onChange={(e) => setBacktestSelection((prev) => ({ ...prev, [m.symbol]: e.target.value }))}
                                  className="px-2 py-1.5 rounded bg-gray-900 border border-gray-700 text-sm focus:border-violet-500 outline-none"
                                >
                                  <option value="">Select a strategy...</option>
                                  {suggested.map((s) => (
                                    <option key={s.id} value={s.id}>{s.name}</option>
                                  ))}
                                </select>
                                <button
                                  onClick={() => {
                                    const strategyId = backtestSelection[m.symbol];
                                    if (!strategyId) return;
                                    navigate(`/backtest?symbol=${encodeURIComponent(m.symbol)}&strategy=${encodeURIComponent(strategyId)}`);
                                  }}
                                  disabled={!backtestSelection[m.symbol]}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                                >
                                  Backtest
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
