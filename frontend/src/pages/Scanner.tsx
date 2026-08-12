import { useEffect, useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { Card, Badge } from '../components/Card';
import { fetchMarkets, runAnalysis } from '../services/api';
import type { Market, Signal } from '../types';

export function Scanner() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [latestSignal, setLatestSignal] = useState<Signal | null>(null);

  useEffect(() => {
    fetchMarkets().then(setMarkets);
  }, []);

  const handleAnalyze = async (symbol: string) => {
    setAnalyzing(symbol);
    try {
      const signal = await runAnalysis(symbol);
      setLatestSignal(signal);
    } finally {
      setAnalyzing(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Market Scanner</h1>
        <p className="text-sm text-gray-400 mt-1">Run TradingAgents analysis on Hyperliquid markets</p>
      </div>

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
              <th className="p-4 font-medium">Signal</th>
              <th className="p-4 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {markets.map((m) => (
              <tr key={m.symbol} className="hover:bg-gray-800/30 transition-colors">
                <td className="p-4 font-medium">{m.symbol} <span className="text-gray-500 font-normal">{m.name}</span></td>
                <td className="p-4 text-gray-400 capitalize">{m.type}</td>
                <td className="p-4">${m.price.toLocaleString()}</td>
                <td className={`p-4 ${m.change24h >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{m.change24h >= 0 ? '+' : ''}{m.change24h}%</td>
                <td className="p-4 text-gray-400">${(m.volume24h / 1e6).toFixed(1)}M</td>
                <td className="p-4 text-gray-400">{m.funding !== undefined ? `${(m.funding * 100).toFixed(4)}%` : '-'}</td>
                <td className="p-4">{m.signal ? <Badge action={m.signal} /> : <span className="text-gray-500">—</span>}</td>
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
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
