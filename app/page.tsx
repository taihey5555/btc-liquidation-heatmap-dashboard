"use client";

import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  fetchExchangeStatus,
  fetchHeatmap,
  fetchLatestObservationReport,
  fetchObservationAnomalies,
  fetchObservationRuns,
  fetchRecentLiquidations,
  type ApiExchangeStatus,
  type ApiLiquidationEvent,
  type ApiObservationAnomaly,
  type ApiObservationReport,
  type ApiObservationRun,
  type HeatmapResponse,
} from "./lib/heatmapApi";

type Candle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

type HeatBand = {
  price: number;
  start: number;
  end: number;
  intensity: number;
};

type ProfileRow = {
  price: number;
  long: number;
  short: number;
};

type DataMode = "mock" | "live";
const liveExchanges = ["binance", "bybit", "okx", "gate", "mexc"];
const showMockToggle = process.env.NEXT_PUBLIC_SHOW_MOCK_TOGGLE === "true";

const defaultPriceMin = 75000;
const defaultPriceMax = 81950;
const chartWidth = 1100;
const chartHeight = 590;
const bottomHeight = 108;
const rangeTickLabels: Record<string, string[]> = {
  "12H": ["-12h", "-10h", "-8h", "-6h", "-4h", "-2h", "now"],
  "24H": ["-24h", "-20h", "-16h", "-12h", "-8h", "-4h", "now"],
  "3D": ["-3d", "-60h", "-48h", "-36h", "-24h", "-12h", "now"],
  "7D": ["-7d", "-6d", "-5d", "-4d", "-3d", "-2d", "-1d", "now"],
  "30D": ["-30d", "-25d", "-20d", "-15d", "-10d", "-5d", "now"],
  "90D": ["-90d", "-75d", "-60d", "-45d", "-30d", "-15d", "now"],
  "180D": ["-180d", "-150d", "-120d", "-90d", "-60d", "-30d", "now"],
  "1Y": ["-1y", "-10m", "-8m", "-6m", "-4m", "-2m", "now"],
};

function seededNoise(index: number) {
  return Math.sin(index * 1.73) * 0.5 + Math.sin(index * 0.41) * 0.34 + Math.cos(index * 0.19) * 0.16;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function roundChart(value: number, digits = 4) {
  return Number(value.toFixed(digits));
}

function pct(value: number) {
  return `${roundChart(value)}%`;
}

function yForPrice(price: number, min = defaultPriceMin, max = defaultPriceMax) {
  return roundChart(chartHeight - ((price - min) / (max - min)) * chartHeight);
}

function xForIndex(index: number, total: number) {
  return roundChart((index / Math.max(1, total - 1)) * chartWidth);
}

function rangeProfile(range: string) {
  const normalized = range.toUpperCase();
  if (normalized === "12H") return { volatility: 0.55, driftScale: 0.45 };
  if (normalized === "24H") return { volatility: 0.72, driftScale: 0.6 };
  if (normalized === "3D") return { volatility: 0.9, driftScale: 0.78 };
  if (normalized === "7D") return { volatility: 1.08, driftScale: 0.95 };
  if (normalized === "30D") return { volatility: 1.22, driftScale: 1.12 };
  if (normalized === "180D" || normalized === "1Y") return { volatility: 1.48, driftScale: 1.38 };
  return { volatility: 1.32, driftScale: 1.24 };
}

function rangeWindow(range: string) {
  const normalized = range.toUpperCase();
  if (normalized === "12H") return 4_000;
  if (normalized === "24H") return 5_000;
  if (normalized === "3D") return 7_000;
  if (normalized === "7D") return 9_000;
  if (normalized === "30D") return 10_000;
  if (normalized === "180D") return 18_000;
  if (normalized === "1Y") return 24_000;
  return 12_000;
}

function roundTick(price: number) {
  return Math.round(price / 500) * 500;
}

function buildPriceTicks(min: number, max: number) {
  const ticks = Array.from({ length: 8 }, (_, index) => roundTick(max - ((max - min) / 7) * index));
  return [...new Set(ticks)].filter((tick) => tick >= min && tick <= max);
}

function buildCandles(range: string): Candle[] {
  let last = 78120;
  const profile = rangeProfile(range);
  const ticks = rangeTickLabels[range] ?? rangeTickLabels["90D"];
  return Array.from({ length: 245 }, (_, index) => {
    const drift = (index < 80 ? 2 : index < 150 ? 8 : index < 190 ? 2 : -18) * profile.driftScale;
    const shock = (index === 160 ? 710 : index > 160 && index < 173 ? -28 : 0) * profile.volatility;
    const change = drift + seededNoise(index) * 48 * profile.volatility + shock;
    const open = last;
    const close = clamp(open + change, 75150, 81650);
    const high = Math.max(open, close) + 22 + Math.abs(seededNoise(index + 8)) * 52;
    const low = Math.min(open, close) - 18 - Math.abs(seededNoise(index + 17)) * 48;
    last = close;
    const tick = ticks[Math.floor((index / 244) * (ticks.length - 1))];
    return { time: tick, open, high, low, close };
  });
}

function buildHeatBands(model: number, threshold: number): HeatBand[] {
  const anchors = [
    81580, 81390, 81220, 81040, 80680, 80440, 80220, 80040, 79840, 79660, 79480, 79270, 79080, 78880,
    78540, 78280, 78060, 77820, 77580, 77390, 77160, 76960, 76780, 76580, 76240, 75980, 75680, 75320,
  ];
  const bands: HeatBand[] = [];
  anchors.forEach((price, anchorIndex) => {
    const rowCount = anchorIndex % 4 === 0 ? 5 : 3;
    for (let row = 0; row < rowCount; row += 1) {
      const start = clamp((anchorIndex * 13 + row * 21 + model * 9) % 185, 0, 214);
      const length = 46 + ((anchorIndex * 19 + row * 17) % 142);
      const intensity = clamp(0.14 + ((anchorIndex + row + model) % 6) * 0.12 + threshold / 360, 0.16, 0.94);
      bands.push({
        price: price - row * 34 + model * 10,
        start,
        end: clamp(start + length, 34, 244),
        intensity,
      });
    }
  });
  bands.push({ price: 79070, start: 8, end: 158, intensity: 1 });
  bands.push({ price: 77490, start: 8, end: 244, intensity: 0.97 });
  bands.push({ price: 76670, start: 8, end: 244, intensity: 0.58 });
  bands.push({ price: 81380, start: 8, end: 244, intensity: 0.48 });
  return bands.filter((band) => band.intensity * 100 >= threshold);
}

function buildRelativeBandsFromBuckets(buckets: HeatmapResponse["buckets"]): HeatBand[] {
  if (buckets.length === 0) {
    return [];
  }
  const maxSignal = Math.max(...buckets.map((bucket) => Math.max(bucket.relative_intensity, bucket.total_score * bucket.confidence)), 0.01);
  return buckets.flatMap((bucket, bucketIndex) => {
    const signal = Math.max(bucket.relative_intensity, bucket.total_score * bucket.confidence);
    const consumedFactor = 1 - clamp(bucket.consumed_score ?? 0, 0, 1) * 0.62;
    const baseIntensity = clamp((signal / maxSignal) * consumedFactor, 0.025, 1);
    return Array.from({ length: 9 }, (_, layer) => {
      const intensity = clamp(Math.pow(baseIntensity, 1.22) * (1 - layer * 0.052), 0.035, 1);
      const start = clamp(4 + ((bucketIndex * 13 + layer * 19) % 188), 0, 236);
      const end = clamp(start + 30 + intensity * 122 + (layer % 4) * 10, start + 18, 244);
      return {
        price: bucket.price_bucket + (layer - 4) * 14,
        start,
        end,
        intensity,
      };
    });
  });
}

function buildProfile(): ProfileRow[] {
  return Array.from({ length: 84 }, (_, index) => {
    const price = defaultPriceMin + (index / 83) * (defaultPriceMax - defaultPriceMin);
    const hot = Math.exp(-Math.pow((price - 77500) / 330, 2)) * 0.95 + Math.exp(-Math.pow((price - 79000) / 520, 2)) * 0.7;
    const upper = Math.exp(-Math.pow((price - 79900) / 390, 2)) * 0.55;
    return {
      price,
      long: clamp((hot + Math.max(0, seededNoise(index + 20)) * 0.28) * 100, 2, 112),
      short: clamp((upper + Math.max(0, seededNoise(index + 4)) * 0.35) * 100, 2, 98),
    };
  });
}

function heatColor(intensity: number) {
  if (intensity > 0.9) return "rgba(246, 255, 0, .92)";
  if (intensity > 0.72) return "rgba(99, 226, 55, .72)";
  if (intensity > 0.52) return "rgba(36, 210, 178, .56)";
  if (intensity > 0.36) return "rgba(46, 142, 190, .36)";
  return "rgba(72, 90, 156, .2)";
}

function formatExchangeWeights(weights: HeatmapResponse["exchange_weights"]) {
  const enabledWeights = weights.filter((weight) => weight.enabled && weight.weight > 0);
  if (enabledWeights.length === 0) {
    return "no OI weights";
  }
  const total = enabledWeights.reduce((sum, weight) => sum + weight.weight, 0) || 1;
  const raw = enabledWeights.map((weight) => ({
    exchange: weight.exchange,
    percent: (weight.weight / total) * 100,
  }));
  const rounded = raw.map((item) => ({ ...item, rounded: Math.floor(item.percent) }));
  let remainder = 100 - rounded.reduce((sum, item) => sum + item.rounded, 0);
  [...rounded]
    .sort((a, b) => (b.percent - Math.floor(b.percent)) - (a.percent - Math.floor(a.percent)))
    .forEach((item) => {
      if (remainder > 0) {
        item.rounded += 1;
        remainder -= 1;
      }
    });
  return rounded.map((item) => `${item.exchange} ${item.rounded}%`).join(" / ");
}

function formatEventTime(ts: number | null | undefined) {
  if (!ts) {
    return "no events";
  }
  return new Date(ts).toLocaleTimeString("ja-JP", { hour12: false });
}

function formatCompactUsd(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "$0";
  }
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B est.`;
  }
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M est.`;
  }
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })} est.`;
}

function uniqueMessages(messages: string[]) {
  const seen = new Set<string>();
  return messages.filter((message) => {
    const key = message.trim().toLowerCase();
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export default function Home() {
  const [model, setModel] = useState(1);
  const [range, setRange] = useState("90D");
  const [currency, setCurrency] = useState<"USD" | "JPY">("USD");
  const [threshold, setThreshold] = useState(3);
  const [dataMode, setDataMode] = useState<DataMode>("live");
  const [apiData, setApiData] = useState<HeatmapResponse | null>(null);
  const [lastLiveData, setLastLiveData] = useState<HeatmapResponse | null>(null);
  const [apiStatus, setApiStatus] = useState<"idle" | "ready" | "fallback">("idle");
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(null);
  const [recentLiquidations, setRecentLiquidations] = useState<ApiLiquidationEvent[]>([]);
  const [exchangeStatuses, setExchangeStatuses] = useState<ApiExchangeStatus[]>([]);
  const [enabledExchanges, setEnabledExchanges] = useState<string[]>(liveExchanges);
  const [observationRun, setObservationRun] = useState<ApiObservationRun | null>(null);
  const [observationReport, setObservationReport] = useState<ApiObservationReport | null>(null);
  const [observationAnomalies, setObservationAnomalies] = useState<ApiObservationAnomaly[]>([]);
  const enabledExchangeKey = enabledExchanges.join(",");
  const timeTicks = rangeTickLabels[range] ?? rangeTickLabels["90D"];
  const mockCandles = useMemo(() => buildCandles(range), [range]);
  const mockHeatBands = useMemo(() => buildHeatBands(model, threshold), [model, threshold]);
  const mockProfile = useMemo(() => buildProfile(), []);
  const activeLiveData = dataMode === "live" && apiStatus === "ready" && apiData?.source === "live" && !apiData.fallback
    ? apiData
    : dataMode === "live" && apiStatus === "fallback" && lastLiveData
      ? lastLiveData
      : null;
  const useApiData = activeLiveData !== null;
  const isLiveInitialLoading = dataMode === "live" && apiStatus === "idle" && apiData === null;
  const isMockFallback = dataMode === "live" && apiStatus === "fallback";
  const useMockData = dataMode === "mock" || isMockFallback;
  const isMockVisual = dataMode === "mock" || (isMockFallback && !lastLiveData) || Boolean(apiData?.fallback && !lastLiveData);
  const candles = useApiData ? activeLiveData.candles : mockCandles;
  const topClusters = useMemo(() => {
    const buckets = activeLiveData?.buckets ?? [];
    return [...buckets]
      .filter((bucket) => bucket.relative_intensity >= 0.18)
      .sort((a, b) => b.relative_intensity - a.relative_intensity)
      .slice(0, 4);
  }, [activeLiveData]);
  const strongestCluster = topClusters[0] ?? null;
  const currentReference = activeLiveData?.current_price ?? candles[candles.length - 1].close;
  const priceBounds = useMemo(() => {
    if (!useApiData || !activeLiveData) {
      return { min: defaultPriceMin, max: defaultPriceMax };
    }
    const windowSize = rangeWindow(range);
    const strongBuckets = [...activeLiveData.buckets]
      .filter((bucket) => Math.abs(bucket.price_bucket - currentReference) <= windowSize)
      .sort((a, b) => b.relative_intensity - a.relative_intensity)
      .slice(0, 10)
      .map((bucket) => bucket.price_bucket);
    const candlePrices = candles.flatMap((candle) => [candle.high, candle.low, candle.close]);
    const bandPrices = activeLiveData.heat_bands
      .filter((band) => Math.abs(band.price - currentReference) <= windowSize)
      .map((band) => band.price);
    const prices = [currentReference, ...strongBuckets, ...candlePrices, ...bandPrices].filter(Number.isFinite);
    const rawMin = Math.min(...prices);
    const rawMax = Math.max(...prices);
    const minSpan = Math.min(windowSize * 1.2, 16_000);
    const span = Math.max(rawMax - rawMin, minSpan);
    const mid = (Math.max(rawMax, currentReference + span * 0.18) + Math.min(rawMin, currentReference - span * 0.18)) / 2;
    return {
      min: roundTick(mid - span * 0.56),
      max: roundTick(mid + span * 0.56),
    };
  }, [activeLiveData, candles, currentReference, range, useApiData]);
  const priceMin = priceBounds.min;
  const priceMax = priceBounds.max;
  const yTicks = useMemo(() => buildPriceTicks(priceMin, priceMax), [priceMin, priceMax]);
  const apiRelativeHeatBands = useMemo(() => (activeLiveData?.buckets ? buildRelativeBandsFromBuckets(activeLiveData.buckets) : []), [activeLiveData]);
  const heatBands = useMemo(() => {
    if (isLiveInitialLoading) {
      return [];
    }
    const sourceBands = useApiData ? apiRelativeHeatBands : mockHeatBands;
    return sourceBands.filter((band) => band.intensity * 100 >= threshold);
  }, [apiRelativeHeatBands, isLiveInitialLoading, mockHeatBands, threshold, useApiData]);
  const profile = useApiData ? activeLiveData.profile : useMockData ? mockProfile : [];
  const last = candles[candles.length - 1].close;
  const currentPriceY = yForPrice(last, priceMin, priceMax);
  const fx = 157;
  const priceLabel = isLiveInitialLoading
    ? "Loading live..."
    : useApiData
    ? activeLiveData.display_price
    : currency === "USD"
      ? `$${last.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
      : `¥${Math.round(last * fx).toLocaleString("ja-JP")}`;
  const dataStatusLabel = dataMode === "mock" ? "mock" : apiStatus === "idle" ? "live loading" : apiStatus === "ready" ? (apiData?.fallback ? "fallback mock" : "live") : "mock fallback";
  const generatedAtLabel = apiData?.generated_at ? new Date(apiData.generated_at * 1000).toLocaleTimeString("ja-JP", { hour12: false }) : "-";
  const refreshLabel = lastRefreshAt ? new Date(lastRefreshAt).toLocaleTimeString("ja-JP", { hour12: false }) : "-";
  const currentPriceSource = isLiveInitialLoading ? "waiting for live API" : useApiData ? activeLiveData.current_price_source : isMockFallback ? "mock fallback after live timeout" : "mock";
  const liveWarnings = apiData?.warnings ?? [];
  const excludedExchanges = apiData?.excluded_exchanges ?? [];
  const statusWarnings = exchangeStatuses
    .filter((status) => status.last_error)
    .map((status) => `${status.exchange}: ${status.last_error}`);
  const visibleWarnings = uniqueMessages([...liveWarnings, ...excludedExchanges, ...statusWarnings]).slice(0, 4);
  const exchangeWeights = useApiData
    ? formatExchangeWeights(activeLiveData.exchange_weights)
    : isLiveInitialLoading
      ? "loading live weights"
      : "mock blend";
  const toggleExchange = (exchange: string) => {
    setEnabledExchanges((current) => {
      if (current.includes(exchange)) {
        return current.length === 1 ? current : current.filter((item) => item !== exchange);
      }
      return [...current, exchange];
    });
  };

  useEffect(() => {
    if (dataMode !== "live") {
      return;
    }

    let cancelled = false;

    const loadLiveHeatmap = () => {
      fetchHeatmap({ symbol: "BTCUSDT", model, currency, range, source: "live", exchanges: enabledExchangeKey.split(",") })
        .then((response) => {
          if (!cancelled) {
            setApiData(response);
            if (response.source === "live" && !response.fallback) {
              setLastLiveData(response);
              setApiStatus("ready");
              setApiError(null);
            } else {
              setApiStatus("fallback");
              setApiError(response.warnings?.[0] ?? "live API returned mock fallback");
            }
            setLastRefreshAt(Date.now());
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setApiData(null);
            setApiStatus("fallback");
            setApiError(error instanceof Error ? error.message : "unknown heatmap fetch error");
            setLastRefreshAt(Date.now());
          }
        });
    };

    loadLiveHeatmap();
    const refreshId = window.setInterval(loadLiveHeatmap, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshId);
    };
  }, [currency, dataMode, enabledExchangeKey, model, range]);

  useEffect(() => {
    if (dataMode !== "live") {
      return;
    }

    let cancelled = false;
    const loadStreamData = () => {
      Promise.all([fetchRecentLiquidations("BTCUSDT", 8), fetchExchangeStatus()])
        .then(([events, statuses]) => {
          if (!cancelled) {
            setRecentLiquidations(events);
            setExchangeStatuses(statuses);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setRecentLiquidations([]);
          }
        });
    };

    loadStreamData();
    const refreshId = window.setInterval(loadStreamData, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(refreshId);
    };
  }, [dataMode]);

  useEffect(() => {
    let cancelled = false;
    const loadObservation = () => {
      Promise.all([fetchObservationRuns(), fetchLatestObservationReport(), fetchObservationAnomalies()])
        .then(([runs, report, anomalies]) => {
          if (!cancelled) {
            setObservationRun(runs[0] ?? null);
            setObservationReport(report);
            setObservationAnomalies(anomalies);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setObservationRun(null);
            setObservationReport(null);
            setObservationAnomalies([]);
          }
        });
    };
    loadObservation();
    const refreshId = window.setInterval(loadObservation, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(refreshId);
    };
  }, []);

  return (
    <main className="terminal-shell">
      {isMockVisual ? <div className="fallback-badge">Fallback: Styled Mock View</div> : null}
      <header className="topbar">
        <div className="title-block">
          <p className="eyebrow">BTCUSDT perpetual / <span className={`data-status ${dataStatusLabel === "live" ? "api" : "mock"}`}>{dataStatusLabel}</span></p>
          <h1>Liquidation Heatmap Dashboard</h1>
        </div>
        <div className="toolbar">
          {showMockToggle ? (
            <Segmented label="Source" value={dataMode.toUpperCase()} items={["MOCK", "LIVE"]} onSelect={(value) => setDataMode(value.toLowerCase() as DataMode)} />
          ) : null}
          <Segmented label="Model" value={`Model ${model}`} items={["Model 1", "Model 2", "Model 3"]} onSelect={(value) => setModel(Number(value.slice(-1)))} />
          <Segmented label="Range" value={range} items={["12H", "24H", "3D", "7D", "30D", "90D", "180D", "1Y"]} onSelect={setRange} />
          <Segmented label="Currency" value={currency} items={["USD", "JPY"]} onSelect={(value) => setCurrency(value as "USD" | "JPY")} />
          <label className="threshold">
            <span>Threshold</span>
            <strong>{threshold}%</strong>
            <input type="range" min="0" max="55" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          </label>
        </div>
      </header>

      <section className="market-strip">
        <div>
          <span>BTCUSDT</span>
          <strong>{priceLabel}</strong>
        </div>
        <div>
          <span>Model Signal</span>
          <strong>Relative M{model}</strong>
        </div>
        <div>
          <span>Strongest Cluster</span>
          <strong>{strongestCluster ? `${Math.round(strongestCluster.relative_intensity * 100)}% @ ${strongestCluster.price_bucket.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "-"}</strong>
        </div>
        <div>
          <span>Range</span>
          <strong>{range}</strong>
        </div>
        <div>
          <span>Exchange Weights</span>
          <strong>{exchangeWeights}</strong>
        </div>
        <div>
          <span>Public Data</span>
          <strong>Estimated</strong>
        </div>
      </section>

      <section className="live-status-strip">
        <span className={`status-pill ${dataStatusLabel === "live" ? "ok" : apiData?.fallback || apiStatus === "fallback" ? "warn" : "muted"}`}>
          {dataStatusLabel.toUpperCase()}
        </span>
        <span className="relative-model-note">RELATIVE HEATMAP / NOT COINGLASS API</span>
        <span>API {API_BASE_URL}</span>
        <span>generated {generatedAtLabel}</span>
        <span>refreshed {refreshLabel}</span>
        <span>freshness {apiData?.data_freshness_ms ?? "-"}ms</span>
        <span>price source {currentPriceSource}</span>
        <span>used {(apiData?.exchanges_used ?? []).join(",") || "-"}</span>
        {apiError ? <strong className="status-error">{apiError}</strong> : null}
        {visibleWarnings.length > 0 ? <strong className="status-warning">{visibleWarnings.join(" / ")}</strong> : null}
      </section>

      <section className="exchange-filter">
        {liveExchanges.map((exchange) => (
          <button
            key={exchange}
            type="button"
            className={enabledExchanges.includes(exchange) ? "enabled" : ""}
            onClick={() => toggleExchange(exchange)}
            disabled={dataMode !== "live"}
          >
            {exchange.toUpperCase()}
          </button>
        ))}
      </section>

      <div className="dashboard-scroll">
        <section className="dashboard-grid">
          {isLiveInitialLoading ? (
            <div className="live-loading-overlay">
              <strong>Connecting to live public market data</strong>
              <span>Waiting for BTCUSDT heatmap response...</span>
            </div>
          ) : null}
          <aside className="scale-panel">
            <span>29.91M</span>
            <div className="heat-scale" />
            <span>0</span>
          </aside>

          <div className="chart-stack">
            <div className="legend">
              <span><i className="legend-heat" />Relative Liquidation Strength</span>
              <span><i className="legend-candle" />Candlestick Chart</span>
            </div>
            <div className={`chart-card ${isMockVisual ? "mock-chart" : ""}`}>
              {isMockVisual ? (
                <div className="mock-chart-ribbon">
                  <strong>Styled mock visualization</strong>
                  <span>Live public endpoints timed out. Mock fallback is for layout and relative-signal preview.</span>
                </div>
              ) : null}
              <svg className="main-chart" viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label="BTCUSDT liquidation heatmap chart">
                <defs>
                  <linearGradient id="chartBase" x1="0" x2="1">
                    <stop offset="0%" stopColor="#320643" />
                    <stop offset="45%" stopColor="#3b064e" />
                    <stop offset="100%" stopColor="#160d2c" />
                  </linearGradient>
                  <linearGradient id="chartShade" x1="0" x2="1">
                    <stop offset="0%" stopColor="rgba(255,255,255,.04)" />
                    <stop offset="58%" stopColor="rgba(255,255,255,0)" />
                    <stop offset="100%" stopColor="rgba(0,0,0,.22)" />
                  </linearGradient>
                </defs>
                <rect width={chartWidth} height={chartHeight} fill="url(#chartBase)" />
                <rect width={chartWidth} height={chartHeight} fill="url(#chartShade)" />
                {yTicks.map((tick) => (
                  <line key={tick} x1="0" x2={chartWidth} y1={yForPrice(tick, priceMin, priceMax)} y2={yForPrice(tick, priceMin, priceMax)} className="grid-line" />
                ))}
                {Array.from({ length: 14 }, (_, index) => (
                  <line key={index} x1={(index / 13) * chartWidth} x2={(index / 13) * chartWidth} y1="0" y2={chartHeight} className="grid-line vertical" />
                ))}
                {heatBands.map((band, index) => {
                  const x = xForIndex(band.start, 244);
                  const bandHeight = 3.2 + band.intensity * 5.2;
                  const y = yForPrice(band.price, priceMin, priceMax) - bandHeight / 2;
                  const width = xForIndex(band.end, 244) - x;
                  return <rect key={`${band.price}-${index}`} x={x} y={y} width={width} height={bandHeight} fill={heatColor(band.intensity)} />;
                })}
                <line x1="0" x2={chartWidth} y1={currentPriceY} y2={currentPriceY} className="current-price-line" />
                {candles.map((candle, index) => {
                  const x = xForIndex(index, candles.length);
                  const open = yForPrice(candle.open, priceMin, priceMax);
                  const close = yForPrice(candle.close, priceMin, priceMax);
                  const high = yForPrice(candle.high, priceMin, priceMax);
                  const low = yForPrice(candle.low, priceMin, priceMax);
                  const up = candle.close >= candle.open;
                  return (
                    <g key={index}>
                      <line x1={x} x2={x} y1={high} y2={low} stroke={up ? "#37f4d0" : "#ff477d"} strokeWidth="1.25" />
                      <rect x={x - 1.9} y={Math.min(open, close)} width="3.8" height={Math.max(2.6, Math.abs(close - open))} fill={up ? "#21e6c3" : "#ff2e73"} stroke="rgba(3,7,12,.45)" strokeWidth=".35" />
                    </g>
                  );
                })}
                <rect x={chartWidth - 150} y={currentPriceY - 13} width="112" height="26" rx="3" className="current-price-label-bg" />
                <text x={chartWidth - 142} y={currentPriceY + 5} className="current-price-label">{priceLabel}</text>
                <text x={chartWidth - 128} y={chartHeight - 38} className="watermark">coinglass</text>
              </svg>
              <div className="y-axis">
                {yTicks.map((tick) => <span key={tick} style={{ top: pct((yForPrice(tick, priceMin, priceMax) / chartHeight) * 100) }}>{tick}</span>)}
              </div>
            </div>
            <div className="time-axis">
              {timeTicks.map((tick) => <span key={tick}>{tick}</span>)}
            </div>
          </div>

          <aside className="profile-panel">
            <div className="profile-grid">
              {profile.filter((row) => row.price >= priceMin && row.price <= priceMax).map((row) => {
                const profileStrength = clamp(Math.max(row.long / 112, row.short / 98), 0.04, 1);
                return (
                <div
                  className="profile-row"
                  key={row.price}
                  style={{
                    top: pct(100 - ((row.price - priceMin) / (priceMax - priceMin)) * 100),
                    opacity: roundChart(0.18 + profileStrength * 0.82, 3),
                  }}
                >
                  <span className="profile-short" style={{ width: pct(row.short) }} />
                  <span className="profile-long" style={{ width: pct(row.long) }} />
                </div>
                );
              })}
              <div className="profile-midline" />
              <div className="profile-current-line" style={{ top: pct((currentPriceY / chartHeight) * 100) }} />
              <div className="profile-curve long-curve" />
              <div className="profile-curve short-curve" />
            </div>
          </aside>

          <div className="bottom-panel">
            <div className="bottom-title">
              <span>Accumulated Longs vs Shorts</span>
              <strong>{model === 3 && dataMode === "live" ? "Net Longs - Shorts / liquidation events adjusted" : "Net Longs - Shorts"}</strong>
            </div>
            <svg viewBox={`0 0 ${chartWidth} ${bottomHeight}`} className="net-chart" role="img" aria-label="Accumulated longs shorts chart">
              <path
                d={candles.map((candle, index) => `${index === 0 ? "M" : "L"} ${xForIndex(index, candles.length)} ${roundChart(82 - seededNoise(index + 11) * 18 - (candle.close - 78000) / 70)}`).join(" ")}
                fill="none"
                stroke="#87a8ef"
                strokeWidth="1.4"
              />
              <path
                d={`${candles.map((candle, index) => `${index === 0 ? "M" : "L"} ${xForIndex(index, candles.length)} ${roundChart(82 - seededNoise(index + 11) * 18 - (candle.close - 78000) / 70)}`).join(" ")} L ${chartWidth} ${bottomHeight} L 0 ${bottomHeight} Z`}
                fill="rgba(77, 111, 178, .35)"
              />
            </svg>
          </div>

          <aside className="liquidation-panel">
            <div className="cluster-summary">
              <div className="cluster-title">Top Relative Clusters</div>
              {topClusters.length === 0 ? (
                <span className="empty-events">Waiting for relative cluster data.</span>
              ) : (
                topClusters.map((bucket) => (
                  <div className={`cluster-item ${(bucket.consumed_score ?? 0) > 0.2 ? "consumed" : ""}`} key={`${bucket.price_bucket}-${bucket.dominant_side}`}>
                    <span className={bucket.dominant_side === "long" ? "long-event" : bucket.dominant_side === "short" ? "short-event" : ""}>
                      {bucket.dominant_side}
                    </span>
                    <strong>{bucket.price_bucket.toLocaleString("en-US", { maximumFractionDigits: 0 })}</strong>
                    <span className="cluster-strength">{Math.round(bucket.relative_intensity * 100)}%</span>
                    <span className="cluster-estimate">{formatCompactUsd(bucket.estimated_liq_usd)}</span>
                    {(bucket.consumed_score ?? 0) > 0.2 ? <span className="cluster-consumed">consumed {Math.round(bucket.consumed_score * 100)}%</span> : null}
                    <span className="cluster-meter" aria-hidden="true">
                      <i style={{ width: `${Math.round(bucket.relative_intensity * 100)}%` }} />
                    </span>
                  </div>
                ))
              )}
            </div>
            <div className="stream-status-row">
              {["binance", "bybit"].map((exchange) => {
                const status = exchangeStatuses.find((item) => item.exchange === exchange);
                const hasRecentMessage = status?.websocket_last_message_ts && lastRefreshAt ? lastRefreshAt - status.websocket_last_message_ts < 10 * 60 * 1000 : false;
                const wsState = status?.websocket_connected && hasRecentMessage ? "ON" : status?.websocket_connected ? "CONNECTED / NO EVENTS" : "OFF";
                return (
                  <span key={exchange} className={wsState === "ON" ? "stream-on" : wsState === "CONNECTED / NO EVENTS" ? "stream-idle" : "stream-off"} title={status?.websocket_status_reason ?? undefined}>
                    {exchange.toUpperCase()} WS {wsState}
                  </span>
                );
              })}
            </div>
            <div className="stream-last-row">
              {["binance", "bybit"].map((exchange) => {
                const status = exchangeStatuses.find((item) => item.exchange === exchange);
                return <span key={exchange}>{exchange}: {formatEventTime(status?.websocket_last_message_ts)}</span>;
              })}
            </div>
            <div className="liquidation-list">
              {recentLiquidations.length === 0 ? (
                <span className="empty-events">
                  No recent liquidation events. {exchangeStatuses.find((item) => item.exchange === "binance")?.websocket_status_reason ?? "Start stream job to collect events."}
                </span>
              ) : (
                recentLiquidations.slice(0, 6).map((event) => (
                  <div className="liquidation-item" key={`${event.exchange}-${event.ts}-${event.side}-${event.price}`}>
                    <span>{event.exchange}</span>
                    <strong className={event.side.includes("long") ? "long-event" : "short-event"}>{event.side.replace("_liquidated", "")}</strong>
                    <span>{event.price.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>
                    <span>${event.notional_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>
                  </div>
                ))
              )}
            </div>
          </aside>

          <aside className="observation-panel">
            <div className="observation-head">
              <span>Observation</span>
              <strong>{observationRun?.status ?? "idle"}</strong>
            </div>
            <div className="observation-grid">
              <span>Fallbacks</span>
              <strong>{observationReport?.report_json.fallback_count ?? 0}</strong>
              <span>Anomalies</span>
              <strong>{observationReport?.report_json.anomaly_count ?? observationAnomalies.length}</strong>
              <span>Top Cluster</span>
              <strong>
                {observationReport?.report_json.top_clusters?.[0]
                  ? `$${observationReport.report_json.top_clusters[0].estimated_liq_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
                  : "none"}
              </strong>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

function Segmented({
  label,
  value,
  items,
  onSelect,
}: {
  label: string;
  value: string;
  items: string[];
  onSelect: (value: string) => void;
}) {
  return (
    <div className="segmented-wrap">
      <span>{label}</span>
      <div className="segmented">
        {items.map((item) => (
          <button key={item} className={item === value ? "active" : ""} onClick={() => onSelect(item)} type="button">
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
