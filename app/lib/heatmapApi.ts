export type ApiCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ApiHeatBand = {
  price: number;
  start: number;
  end: number;
  intensity: number;
};

export type ApiProfileRow = {
  price: number;
  long: number;
  short: number;
};

export type ApiNetPoint = {
  time: string;
  value: number;
};

export type ApiExchangeWeight = {
  exchange: string;
  weight: number;
  enabled: boolean;
  open_interest_usd?: number | null;
};

export type ApiLiquidationEvent = {
  exchange: string;
  symbol: string;
  ts: number;
  side: string;
  price: number;
  quantity: number;
  notional_usd: number;
};

export type ApiExchangeStatus = {
  exchange: string;
  enabled: boolean;
  websocket_connected: boolean;
  websocket_last_message_ts: number | null;
  websocket_last_error: string | null;
};

export type ApiObservationRun = {
  id: number;
  started_at: number;
  ended_at: number | null;
  symbol: string;
  interval_seconds: number;
  status: string;
  notes: string | null;
};

export type ApiObservationReport = {
  id: number;
  run_id: number;
  created_at: number;
  period_start: number;
  period_end: number;
  report_json: {
    snapshot_count?: number;
    fallback_count?: number;
    anomaly_count?: number;
    top_clusters?: Array<{ direction: string; price_min: number; price_max: number; estimated_liq_usd: number }>;
  };
  report_markdown: string;
};

export type ApiObservationAnomaly = {
  id: number | null;
  run_id: number;
  ts: number;
  symbol: string;
  severity: string;
  anomaly_type: string;
  exchange: string | null;
  message: string;
};

export type HeatmapResponse = {
  symbol: string;
  model: number;
  currency: "USD" | "JPY";
  range: string;
  source: string;
  fallback: boolean;
  exchanges_used: string[];
  generated_at: number | null;
  warnings: string[];
  data_freshness_ms: number | null;
  display_price: string;
  last_price_usd: number;
  fx_usd_jpy: number;
  candles: ApiCandle[];
  heat_bands: ApiHeatBand[];
  profile: ApiProfileRow[];
  net: ApiNetPoint[];
  exchange_weights: ApiExchangeWeight[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_HEATMAP_API_URL ?? "http://127.0.0.1:8000";

export async function fetchHeatmap(params: {
  symbol: string;
  model: number;
  currency: "USD" | "JPY";
  range: string;
  source: "mock" | "live";
  exchanges?: string[];
}): Promise<HeatmapResponse> {
  const searchParams = new URLSearchParams({
    symbol: params.symbol,
    model: String(params.model),
    currency: params.currency,
    range: params.range.toLowerCase(),
    source: params.source,
  });
  if (params.exchanges && params.exchanges.length > 0) {
    searchParams.set("exchanges", params.exchanges.join(","));
  }
  const response = await fetch(`${API_BASE_URL}/api/heatmap?${searchParams.toString()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Heatmap API failed with ${response.status}`);
  }

  return response.json() as Promise<HeatmapResponse>;
}

export async function fetchRecentLiquidations(symbol = "BTCUSDT", limit = 12): Promise<ApiLiquidationEvent[]> {
  const searchParams = new URLSearchParams({ symbol, limit: String(limit) });
  const response = await fetch(`${API_BASE_URL}/api/liquidations/recent?${searchParams.toString()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Recent liquidations API failed with ${response.status}`);
  }
  return response.json() as Promise<ApiLiquidationEvent[]>;
}

export async function fetchExchangeStatus(): Promise<ApiExchangeStatus[]> {
  const response = await fetch(`${API_BASE_URL}/api/exchanges/status`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Exchange status API failed with ${response.status}`);
  }
  return response.json() as Promise<ApiExchangeStatus[]>;
}

export async function fetchObservationRuns(): Promise<ApiObservationRun[]> {
  const response = await fetch(`${API_BASE_URL}/api/observation/runs`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Observation runs API failed with ${response.status}`);
  }
  return response.json() as Promise<ApiObservationRun[]>;
}

export async function fetchLatestObservationReport(): Promise<ApiObservationReport | null> {
  const response = await fetch(`${API_BASE_URL}/api/observation/reports/latest`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Observation report API failed with ${response.status}`);
  }
  return response.json() as Promise<ApiObservationReport | null>;
}

export async function fetchObservationAnomalies(runId = "latest"): Promise<ApiObservationAnomaly[]> {
  const response = await fetch(`${API_BASE_URL}/api/observation/anomalies?run_id=${runId}`, { cache: "no-store" });
  if (!response.ok) {
    if (response.status === 404) {
      return [];
    }
    throw new Error(`Observation anomalies API failed with ${response.status}`);
  }
  return response.json() as Promise<ApiObservationAnomaly[]>;
}
