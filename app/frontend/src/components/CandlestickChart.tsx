import { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type CandlestickData,
  type IChartApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { RotateCcw } from 'lucide-react';
import type { BacktestResult, BacktestTrade } from '../types';

type PriceBar = BacktestResult['price'][number];

interface CandlestickChartProps {
  price: PriceBar[];
  trades: BacktestTrade[];
}

interface HoveredBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  events: TradeEvent[];
}

interface TradeEvent {
  kind: 'entry' | 'exit';
  trade: BacktestTrade;
}

function toTimestamp(time: string): UTCTimestamp {
  return Math.floor(new Date(time).getTime() / 1000) as UTCTimestamp;
}

function formatExitReason(reason: BacktestTrade['exitReason']) {
  return reason.replaceAll('_', ' ');
}

function formatPrice(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPnl(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function CandlestickChart({ price, trades }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hoveredBar, setHoveredBar] = useState<HoveredBar | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !price.length) {
      chartRef.current = null;
      return;
    }

    const chart = createChart(container, {
      width: container.clientWidth || 1,
      height: container.clientHeight || 1,
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6b7280', width: 1, style: 2 },
        horzLine: { color: '#6b7280', width: 1, style: 2 },
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceLineVisible: false,
    });
    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: 'volume' },
        priceScaleId: '',
        color: '#374151',
        base: 0,
      },
      1,
    );

    const candleData: CandlestickData<Time>[] = price.map((bar) => ({
      time: toTimestamp(bar.time),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }));
    const volumeData = price.map((bar) => ({
      time: toTimestamp(bar.time),
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
    }));
    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);

    const validTimes = new Set(candleData.map((bar) => bar.time));
    const markers: SeriesMarker<Time>[] = [];
    const eventsByTime = new Map<number, TradeEvent[]>();
    const addEvent = (time: UTCTimestamp, event: TradeEvent) => {
      const events = eventsByTime.get(time) ?? [];
      events.push(event);
      eventsByTime.set(time, events);
    };
    for (const trade of trades) {
      const entryTime = toTimestamp(trade.entryTime);
      if (validTimes.has(entryTime)) {
        const isLong = trade.side === 'LONG';
        markers.push({
          time: entryTime,
          position: isLong ? 'belowBar' : 'aboveBar',
          shape: isLong ? 'arrowUp' : 'arrowDown',
          color: isLong ? '#10b981' : '#ef4444',
          size: 1,
        });
        addEvent(entryTime, { kind: 'entry', trade });
      }

      const exitTime = toTimestamp(trade.exitTime);
      if (validTimes.has(exitTime)) {
        const isLong = trade.side === 'LONG';
        const isSignalExit = trade.exitReason === 'signal';
        markers.push({
          time: exitTime,
          position: isLong ? 'aboveBar' : 'belowBar',
          shape: isSignalExit ? 'circle' : 'square',
          color: isSignalExit ? '#f59e0b' : '#f97316',
          size: 1,
        });
        addEvent(exitTime, { kind: 'exit', trade });
      }
    }
    markers.sort((a, b) => Number(a.time) - Number(b.time));
    const seriesMarkers = createSeriesMarkers(candleSeries, markers);

    chart.timeScale().fitContent();
    const panes = chart.panes();
    if (panes.length > 1) {
      panes[1].setHeight(Math.min(80, Math.max(64, container.clientHeight * 0.25)));
    }

    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      if (!param.point || typeof param.time !== 'number') {
        setHoveredBar(null);
        return;
      }
      const data = param.seriesData.get(candleSeries);
      if (!data || !('open' in data) || !('high' in data) || !('low' in data) || !('close' in data)) {
        setHoveredBar(null);
        return;
      }
      setHoveredBar({
        time: param.time,
        open: data.open,
        high: data.high,
        low: data.low,
        close: data.close,
        events: eventsByTime.get(param.time) ?? [],
      });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    const resizeObserver = new ResizeObserver(() => {
      if (container.clientWidth && container.clientHeight) {
        chart.resize(container.clientWidth, container.clientHeight);
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      seriesMarkers.detach();
      chart.remove();
      chartRef.current = null;
      setHoveredBar(null);
    };
  }, [price, trades]);

  function resetView() {
    chartRef.current?.timeScale().fitContent();
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-500">
        <span className="text-gray-400">Markers:</span>
        <span className="text-emerald-400">▲ long entry</span>
        <span className="text-rose-400">▼ short entry</span>
        <span className="text-amber-400">● signal exit</span>
        <span className="text-orange-400">■ protective exit</span>
      </div>
      {!price.length ? (
        <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-gray-500">No price data available.</div>
      ) : (
        <>
          <div ref={containerRef} className="min-h-0 flex-1 w-full" />
          <button
            type="button"
            onClick={resetView}
            title="Fit full price range"
            className="absolute right-2 top-2 z-10 rounded-md bg-gray-800 p-1 text-gray-300 transition-colors hover:bg-gray-700"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          {hoveredBar && (
            <div className="pointer-events-none absolute left-2 top-2 z-10 rounded-md border border-gray-700 bg-gray-900/90 px-3 py-2 text-xs text-gray-300 shadow-lg">
              <div className="mb-1 text-gray-500">{new Date(Number(hoveredBar.time) * 1000).toLocaleString()}</div>
              <div className="grid grid-cols-4 gap-3">
                <span>
                  O <strong className="text-gray-100">{formatPrice(hoveredBar.open)}</strong>
                </span>
                <span>
                  H <strong className="text-gray-100">{formatPrice(hoveredBar.high)}</strong>
                </span>
                <span>
                  L <strong className="text-gray-100">{formatPrice(hoveredBar.low)}</strong>
                </span>
                <span>
                  C <strong className="text-gray-100">{formatPrice(hoveredBar.close)}</strong>
                </span>
              </div>
              {hoveredBar.events.length > 0 && (
                <div className="mt-2 space-y-1 border-t border-gray-700 pt-2">
                  {hoveredBar.events.map((event, index) => (
                    <div key={`${event.kind}-${event.trade.entryTime}-${index}`} className="flex flex-wrap gap-x-2">
                      <span className={event.kind === 'entry' ? 'text-gray-200' : 'text-amber-300'}>
                        {event.trade.side} {event.kind}
                      </span>
                      {event.kind === 'exit' && <span>· {formatExitReason(event.trade.exitReason)}</span>}
                      <span>· net PnL {formatPnl(event.trade.netPnl)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
