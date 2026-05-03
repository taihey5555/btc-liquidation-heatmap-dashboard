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


class HeatmapResponse(BaseModel):
    symbol: str
    model: int
    currency: str
    range: str
    source: str = "api-mock"
    fallback: bool = False
    exchanges_used: list[str] = []
    generated_at: int | None = None
    warnings: list[str] = []
    data_freshness_ms: int | None = None
    display_price: str
    last_price_usd: float
    fx_usd_jpy: float
    candles: list[Candle]
    heat_bands: list[HeatBand]
    profile: list[ProfileRow]
    net: list[NetPoint]
    buckets: list[HeatmapBucket]
    exchange_weights: list[ExchangeWeight]


class ExchangeStatus(BaseModel):
    exchange: str
    enabled: bool
    last_success_ts: int | None = None
    last_error: str | None = None
    latency_ms: int | None = None


class LiquidationEvent(BaseModel):
    exchange: str
    symbol: str
    ts: int
    side: str
    price: float
    quantity: float
    notional_usd: float
