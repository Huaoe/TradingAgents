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
}

function toTimestamp(time: string): UTCTimestamp {
  return Math.floor(new Date(time).getTime() / 1000) as UTCTimestamp;
}

function exitLabel(reason: BacktestTrade['exitReason']) {
  switch (reason) {
    case 'stop_loss':
      return 'SL';
    case 'take_profit':
      return 'TP';
    case 'trailing_stop':
      return 'Trail';
    case 'end_of_backtest':
      return 'End';
    default:
      return 'Signal';
  }
}

function formatPrice(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
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
        background: { type: ColorType.Solid, color: '#11131a' },
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
    for (const trade of trades) {
      const entryTime = toTimestamp(trade.entryTime);
      if (validTimes.has(entryTime)) {
        const isLong = trade.side === 'LONG';
        markers.push({
          time: entryTime,
          position: isLong ? 'belowBar' : 'aboveBar',
          shape: isLong ? 'arrowUp' : 'arrowDown',
          color: isLong ? '#10b981' : '#ef4444',
          text: isLong ? 'Long entry' : 'Short entry',
        });
      }

      const exitTime = toTimestamp(trade.exitTime);
      if (validTimes.has(exitTime)) {
        const isLong = trade.side === 'LONG';
        const isSignalExit = trade.exitReason === 'signal';
        markers.push({
          time: exitTime,
          position: isLong ? 'aboveBar' : 'belowBar',
          shape: isSignalExit ? (isLong ? 'arrowDown' : 'arrowUp') : 'square',
          color: isSignalExit ? '#f59e0b' : '#f97316',
          text: exitLabel(trade.exitReason),
        });
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
    <div className="relative h-full min-h-0 w-full">
      {!price.length ? (
        <div className="flex h-full items-center justify-center text-sm text-gray-500">No price data available.</div>
      ) : (
        <>
          <div ref={containerRef} className="h-full w-full" />
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
            </div>
          )}
        </>
      )}
    </div>
  );
}
