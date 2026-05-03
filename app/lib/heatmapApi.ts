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
}): Promise<HeatmapResponse> {
  const searchParams = new URLSearchParams({
    symbol: params.symbol,
    model: String(params.model),
    currency: params.currency,
    range: params.range.toLowerCase(),
    source: params.source,
  });
  const response = await fetch(`${API_BASE_URL}/api/heatmap?${searchParams.toString()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Heatmap API failed with ${response.status}`);
  }

  return response.json() as Promise<HeatmapResponse>;
}
