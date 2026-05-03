"use client";

import { useEffect, useMemo, useState } from "react";
import {
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

const priceMin = 75000;
const priceMax = 81950;
const chartWidth = 1080;
const chartHeight = 650;
const bottomHeight = 118;
const yTicks = [81950, 81000, 80000, 79000, 78000, 77000, 76000, 75000];
const xTicks = [
  "05-02 15:00",
  "05-02 17:20",
  "05-02 19:40",
  "05-02 22:00",
  "05-03 00:20",
  "05-03 02:40",
  "05-03 05:00",
  "05-03 07:20",
  "05-03 09:40",
  "05-03 12:00",
  "05-03 14:20",
];

function seededNoise(index: number) {
  return Math.sin(index * 1.73) * 0.5 + Math.sin(index * 0.41) * 0.34 + Math.cos(index * 0.19) * 0.16;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function yForPrice(price: number) {
  return chartHeight - ((price - priceMin) / (priceMax - priceMin)) * chartHeight;
}

function xForIndex(index: number, total: number) {
  return (index / Math.max(1, total - 1)) * chartWidth;
}

function buildCandles(): Candle[] {
  let last = 78120;
  return Array.from({ length: 245 }, (_, index) => {
    const drift = index < 80 ? 2 : index < 150 ? 8 : index < 190 ? 2 : -18;
    const shock = index === 160 ? 710 : index > 160 && index < 173 ? -28 : 0;
    const change = drift + seededNoise(index) * 48 + shock;
    const open = last;
    const close = clamp(open + change, 75150, 81650);
    const high = Math.max(open, close) + 22 + Math.abs(seededNoise(index + 8)) * 52;
    const low = Math.min(open, close) - 18 - Math.abs(seededNoise(index + 17)) * 48;
    last = close;
    const tick = xTicks[Math.floor((index / 244) * (xTicks.length - 1))];
    return { time: tick, open, high, low, close };
  });
}

function buildHeatBands(model: number, threshold: number): HeatBand[] {
  const anchors = [
    81280, 80980, 80310, 79900, 79680, 79300, 79080, 78720, 77940, 77500, 76960, 76780, 75880, 75320,
  ];
  const bands: HeatBand[] = [];
  anchors.forEach((price, anchorIndex) => {
    const rowCount = anchorIndex % 3 === 0 ? 4 : 3;
    for (let row = 0; row < rowCount; row += 1) {
      const start = clamp((anchorIndex * 17 + row * 29 + model * 9) % 175, 0, 210);
      const length = 70 + ((anchorIndex * 23 + row * 13) % 130);
      const intensity = clamp(0.26 + ((anchorIndex + row + model) % 5) * 0.16 + threshold / 250, 0.28, 0.98);
      bands.push({
        price: price - row * 72 + model * 18,
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

function buildProfile(): ProfileRow[] {
  return Array.from({ length: 84 }, (_, index) => {
    const price = priceMin + (index / 83) * (priceMax - priceMin);
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
  if (intensity > 0.9) return "rgba(245, 255, 0, .95)";
  if (intensity > 0.72) return "rgba(80, 224, 62, .84)";
  if (intensity > 0.52) return "rgba(36, 206, 168, .68)";
  if (intensity > 0.36) return "rgba(49, 135, 184, .5)";
  return "rgba(62, 62, 142, .42)";
}

export default function Home() {
  const [model, setModel] = useState(1);
  const [range, setRange] = useState("90D");
  const [currency, setCurrency] = useState<"USD" | "JPY">("USD");
  const [threshold, setThreshold] = useState(18);
  const [dataMode, setDataMode] = useState<DataMode>("mock");
  const [apiData, setApiData] = useState<HeatmapResponse | null>(null);
  const [apiStatus, setApiStatus] = useState<"idle" | "ready" | "fallback">("idle");
  const [recentLiquidations, setRecentLiquidations] = useState<ApiLiquidationEvent[]>([]);
  const [exchangeStatuses, setExchangeStatuses] = useState<ApiExchangeStatus[]>([]);
  const [enabledExchanges, setEnabledExchanges] = useState<string[]>(liveExchanges);
  const [observationRun, setObservationRun] = useState<ApiObservationRun | null>(null);
  const [observationReport, setObservationReport] = useState<ApiObservationReport | null>(null);
  const [observationAnomalies, setObservationAnomalies] = useState<ApiObservationAnomaly[]>([]);
  const enabledExchangeKey = enabledExchanges.join(",");
  const mockCandles = useMemo(() => buildCandles(), []);
  const mockHeatBands = useMemo(() => buildHeatBands(model, threshold), [model, threshold]);
  const mockProfile = useMemo(() => buildProfile(), []);
  const useApiData = dataMode === "live" && apiData !== null && apiStatus === "ready";
  const candles = useApiData ? apiData.candles : mockCandles;
  const heatBands = useMemo(() => {
    const sourceBands = useApiData ? apiData.heat_bands : mockHeatBands;
    return sourceBands.filter((band) => band.intensity * 100 >= threshold);
  }, [apiData, mockHeatBands, threshold, useApiData]);
  const profile = useApiData ? apiData.profile : mockProfile;
  const last = candles[candles.length - 1].close;
  const fx = 157;
  const priceLabel = useApiData
    ? apiData.display_price
    : currency === "USD"
      ? `$${last.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
      : `¥${Math.round(last * fx).toLocaleString("ja-JP")}`;
  const dataStatusLabel = dataMode === "mock" ? "mock" : apiStatus === "ready" ? (apiData?.fallback ? "fallback mock" : "live") : "mock fallback";
  const exchangeWeights = useApiData
    ? apiData.exchange_weights
        .filter((weight) => weight.enabled)
        .map((weight) => `${weight.exchange} ${(weight.weight * 100).toFixed(0)}%`)
        .join(" / ")
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
            setApiStatus("ready");
          }
        })
        .catch(() => {
          if (!cancelled) {
            setApiData(null);
            setApiStatus("fallback");
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
      <header className="topbar">
        <div className="title-block">
          <p className="eyebrow">BTCUSDT perpetual / <span className={`data-status ${dataStatusLabel === "live" ? "api" : "mock"}`}>{dataStatusLabel}</span></p>
          <h1>Liquidation Heatmap Dashboard</h1>
        </div>
        <div className="toolbar">
          <Segmented label="Source" value={dataMode.toUpperCase()} items={["MOCK", "LIVE"]} onSelect={(value) => setDataMode(value.toLowerCase() as DataMode)} />
          <Segmented label="Model" value={`Model ${model}`} items={["Model 1", "Model 2", "Model 3"]} onSelect={(value) => setModel(Number(value.slice(-1)))} />
          <Segmented label="Range" value={range} items={["12H", "24H", "3D", "7D", "30D", "90D", "180D", "1Y"]} onSelect={setRange} />
          <Segmented label="Currency" value={currency} items={["USD", "JPY"]} onSelect={(value) => setCurrency(value as "USD" | "JPY")} />
          <label className="threshold">
            <span>Threshold</span>
            <strong>{threshold}%</strong>
            <input type="range" min="0" max="70" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          </label>
        </div>
      </header>

      <section className="market-strip">
        <div>
          <span>BTCUSDT</span>
          <strong>{priceLabel}</strong>
        </div>
        <div>
          <span>Model</span>
          <strong>{model}</strong>
        </div>
        <div>
          <span>Visible Bands</span>
          <strong>{heatBands.length}</strong>
        </div>
        <div>
          <span>Range</span>
          <strong>{range}</strong>
        </div>
        <div>
          <span>Exchange Weights</span>
          <strong>{exchangeWeights}</strong>
        </div>
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
          <aside className="scale-panel">
            <span>29.91M</span>
            <div className="heat-scale" />
            <span>0</span>
          </aside>

          <div className="chart-stack">
            <div className="legend">
              <span><i className="legend-heat" />Liquidation Leverage</span>
              <span><i className="legend-candle" />Candlestick Chart</span>
            </div>
            <div className="chart-card">
              <svg className="main-chart" viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label="BTCUSDT liquidation heatmap mock chart">
                <defs>
                  <linearGradient id="chartBase" x1="0" x2="1">
                    <stop offset="0%" stopColor="#4d0066" />
                    <stop offset="55%" stopColor="#4b0060" />
                    <stop offset="100%" stopColor="#2d064d" />
                  </linearGradient>
                </defs>
                <rect width={chartWidth} height={chartHeight} fill="url(#chartBase)" />
                {yTicks.map((tick) => (
                  <line key={tick} x1="0" x2={chartWidth} y1={yForPrice(tick)} y2={yForPrice(tick)} className="grid-line" />
                ))}
                {Array.from({ length: 12 }, (_, index) => (
                  <line key={index} x1={(index / 11) * chartWidth} x2={(index / 11) * chartWidth} y1="0" y2={chartHeight} className="grid-line vertical" />
                ))}
                {heatBands.map((band, index) => {
                  const x = xForIndex(band.start, 244);
                  const y = yForPrice(band.price) - 4;
                  const width = xForIndex(band.end, 244) - x;
                  return <rect key={`${band.price}-${index}`} x={x} y={y} width={width} height={8 + band.intensity * 11} fill={heatColor(band.intensity)} opacity={0.92} />;
                })}
                {candles.map((candle, index) => {
                  const x = xForIndex(index, candles.length);
                  const open = yForPrice(candle.open);
                  const close = yForPrice(candle.close);
                  const high = yForPrice(candle.high);
                  const low = yForPrice(candle.low);
                  const up = candle.close >= candle.open;
                  return (
                    <g key={index}>
                      <line x1={x} x2={x} y1={high} y2={low} stroke={up ? "#21e2c0" : "#ff3b74"} strokeWidth="1.1" />
                      <rect x={x - 2.1} y={Math.min(open, close)} width="4.2" height={Math.max(2.5, Math.abs(close - open))} fill={up ? "#20e0bb" : "#ff316f"} />
                    </g>
                  );
                })}
                <text x={chartWidth - 120} y={chartHeight - 42} className="watermark">coinglass</text>
              </svg>
              <div className="y-axis">
                {yTicks.map((tick) => <span key={tick} style={{ top: `${(yForPrice(tick) / chartHeight) * 100}%` }}>{tick}</span>)}
              </div>
            </div>
            <div className="time-axis">
              {xTicks.map((tick) => <span key={tick}>{tick}</span>)}
            </div>
          </div>

          <aside className="profile-panel">
            <div className="profile-grid">
              {profile.map((row) => (
                <div className="profile-row" key={row.price} style={{ top: `${100 - ((row.price - priceMin) / (priceMax - priceMin)) * 100}%` }}>
                  <span className="profile-short" style={{ width: `${row.short}%` }} />
                  <span className="profile-long" style={{ width: `${row.long}%` }} />
                </div>
              ))}
              <div className="profile-midline" />
              <div className="profile-curve long-curve" />
              <div className="profile-curve short-curve" />
            </div>
          </aside>

          <div className="bottom-panel">
            <div className="bottom-title">
              <span>Accumulated Longs vs Shorts</span>
              <strong>{model === 3 && dataMode === "live" ? "Net Longs - Shorts / liquidation events adjusted" : "Net Longs - Shorts"}</strong>
            </div>
            <svg viewBox={`0 0 ${chartWidth} ${bottomHeight}`} className="net-chart" role="img" aria-label="Accumulated longs shorts mock chart">
              <path
                d={candles.map((candle, index) => `${index === 0 ? "M" : "L"} ${xForIndex(index, candles.length)} ${82 - seededNoise(index + 11) * 18 - (candle.close - 78000) / 70}`).join(" ")}
                fill="none"
                stroke="#87a8ef"
                strokeWidth="1.4"
              />
              <path
                d={`${candles.map((candle, index) => `${index === 0 ? "M" : "L"} ${xForIndex(index, candles.length)} ${82 - seededNoise(index + 11) * 18 - (candle.close - 78000) / 70}`).join(" ")} L ${chartWidth} ${bottomHeight} L 0 ${bottomHeight} Z`}
                fill="rgba(77, 111, 178, .35)"
              />
            </svg>
          </div>

          <aside className="liquidation-panel">
            <div className="stream-status-row">
              {["binance", "bybit"].map((exchange) => {
                const status = exchangeStatuses.find((item) => item.exchange === exchange);
                return (
                  <span key={exchange} className={status?.websocket_connected ? "stream-on" : "stream-off"}>
                    {exchange.toUpperCase()} WS {status?.websocket_connected ? "ON" : "OFF"}
                  </span>
                );
              })}
            </div>
            <div className="liquidation-list">
              {recentLiquidations.length === 0 ? (
                <span className="empty-events">No recent liquidation events</span>
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
