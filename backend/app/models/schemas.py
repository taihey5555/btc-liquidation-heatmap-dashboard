from pydantic import BaseModel, Field


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float


class HeatBand(BaseModel):
    price: float
    start: int
    end: int
    intensity: float = Field(ge=0, le=1)


class ProfileRow(BaseModel):
    price: float
    long: float
    short: float


class NetPoint(BaseModel):
    time: str
    value: float


class ExchangeWeight(BaseModel):
    exchange: str
    weight: float
    enabled: bool = True
    open_interest_usd: float | None = None


class HeatmapBucket(BaseModel):
    ts: int
    price_bucket: float
    long_liq_usd: float
    short_liq_usd: float
    total_score: float
    confidence: float
    relative_intensity: float = Field(default=0, ge=0, le=1)
    dominant_side: str = "balanced"
    estimated_liq_usd: float = 0
    consumed_score: float = Field(default=0, ge=0, le=1)


class HeatmapResponse(BaseModel):
    symbol: str
    model: int
    currency: str
    range: str
    source: str = "api-mock"
    fallback: bool = False
    exchanges_used: list[str] = []
    excluded_exchanges: list[str] = []
    generated_at: int | None = None
    warnings: list[str] = []
    data_freshness_ms: int | None = None
    current_price: float | None = None
    current_price_source: str = "mock"
    display_price: str
    last_price_usd: float
    fx_usd_jpy: float
    candles: list[Candle]
    heat_bands: list[HeatBand]
    profile: list[ProfileRow]
    net: list[NetPoint]
    buckets: list[HeatmapBucket]
    exchange_weights: list[ExchangeWeight]


class SignalZone(BaseModel):
    price: float
    side: str
    distance_pct: float
    relative_intensity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    consumed_score: float = Field(ge=0, le=1)
    total_score: float = Field(ge=0, le=1)
    estimated_liq_usd: float


class LiquidationSignalResponse(BaseModel):
    symbol: str
    model: int
    range: str
    source: str
    fallback: bool
    current_price: float
    generated_at: int | None = None
    data_freshness_ms: int | None = None
    exchanges_used: list[str] = []
    warnings: list[str] = []
    nearest_long_liq_below: list[SignalZone]
    nearest_short_liq_above: list[SignalZone]
    strongest_clusters: list[SignalZone]


class TopClusterZone(BaseModel):
    range: str
    model: int
    price: float
    side: str
    distance_pct: float
    relative_intensity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    consumed_score: float = Field(ge=0, le=1)
    total_score: float = Field(ge=0, le=1)
    estimated_liq_usd: float


class TopClustersResponse(BaseModel):
    symbol: str
    source: str
    fallback: bool
    current_price: float
    generated_at: int | None = None
    data_freshness_ms: int | None = None
    ranges: list[str]
    exchanges_used: list[str] = []
    warnings: list[str] = []
    top_clusters: list[TopClusterZone]
    nearest_long_liq_below: list[TopClusterZone]
    nearest_short_liq_above: list[TopClusterZone]


class ExchangeStatus(BaseModel):
    exchange: str
    enabled: bool
    last_success_ts: int | None = None
    last_error: str | None = None
    latency_ms: int | None = None
    websocket_connected: bool = False
    websocket_last_message_ts: int | None = None
    websocket_last_error: str | None = None
    websocket_status_reason: str | None = None
    data_fields_available: list[str] = []


class LiquidationEvent(BaseModel):
    exchange: str
    symbol: str
    ts: int
    side: str
    price: float
    quantity: float
    notional_usd: float
    raw_json: dict | None = None


class ObservationRun(BaseModel):
    id: int
    started_at: int
    ended_at: int | None = None
    symbol: str
    interval_seconds: int
    status: str
    notes: str | None = None


class ObservationClusterEvent(BaseModel):
    id: int | None = None
    run_id: int
    ts: int
    symbol: str
    model: int
    direction: str
    price_min: float
    price_max: float
    estimated_liq_usd: float
    score: float
    confidence: float
    exchanges_used: list[str]
    message_hash: str


class ObservationAnomaly(BaseModel):
    id: int | None = None
    run_id: int
    ts: int
    symbol: str
    severity: str
    anomaly_type: str
    exchange: str | None = None
    message: str
    raw_json: dict = {}


class ObservationReport(BaseModel):
    id: int
    run_id: int
    created_at: int
    period_start: int
    period_end: int
    report_json: dict
    report_markdown: str
