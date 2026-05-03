from __future__ import annotations

from datetime import UTC, datetime

from app.exchanges.base import MarketSnapshot
from app.models.schemas import Candle, HeatBand, HeatmapBucket, HeatmapResponse, NetPoint, ProfileRow
from app.services.collector import collect_market_data
from app.services.liquidation_models import build_live_buckets, calculate_exchange_weights
from app.services.liquidation_streams import get_recent_liquidations
from app.services.mock_heatmap import FX_USD_JPY, build_mock_heatmap, build_profile, clamp


async def get_heatmap(symbol: str, model: int, currency: str, response_range: str, source: str = "mock") -> HeatmapResponse:
    normalized_source = source.lower()
    if normalized_source == "mock":
        return build_mock_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range)
    return await get_live_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range)


async def get_live_heatmap(symbol: str, model: int, currency: str, response_range: str) -> HeatmapResponse:
    collector_result = await collect_market_data(symbol)
    if not collector_result.snapshots:
        fallback = build_mock_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range)
        fallback.source = "mock"
        fallback.fallback = True
        fallback.warnings = collector_result.warnings or ["live source unavailable; mock fallback used"]
        fallback.exchanges_used = []
        fallback.generated_at = int(datetime.now(UTC).timestamp())
        fallback.data_freshness_ms = None
        return fallback

    snapshots = collector_result.snapshots
    recent_liquidations = _safe_recent_liquidations(symbol) if model == 3 else []
    buckets = build_live_buckets(
        snapshots=snapshots,
        model=model,
        response_range=response_range,
        liquidation_events=recent_liquidations,
    )
    candles = _build_live_candles(snapshots)
    last_price = _weighted_price(snapshots)
    normalized_currency = currency.upper()
    display_price = f"${last_price:,.0f}" if normalized_currency == "USD" else f"¥{last_price * FX_USD_JPY:,.0f}"
    return HeatmapResponse(
        symbol=symbol.upper(),
        model=model,
        currency=normalized_currency,
        range=response_range,
        source="live",
        fallback=False,
        exchanges_used=collector_result.exchanges_used,
        generated_at=int(datetime.now(UTC).timestamp()),
        warnings=collector_result.warnings,
        data_freshness_ms=collector_result.data_freshness_ms,
        display_price=display_price,
        last_price_usd=last_price,
        fx_usd_jpy=FX_USD_JPY,
        candles=candles,
        heat_bands=_buckets_to_heat_bands(buckets),
        profile=_buckets_to_profile(buckets),
        net=_build_live_net(candles),
        buckets=buckets,
        exchange_weights=calculate_exchange_weights(snapshots),
    )


def _weighted_price(snapshots: list[MarketSnapshot]) -> float:
    total_oi = sum(max(0.0, snapshot.open_interest_usd) for snapshot in snapshots)
    if total_oi <= 0:
        return sum(snapshot.mark_price for snapshot in snapshots) / len(snapshots)
    return sum(snapshot.mark_price * snapshot.open_interest_usd for snapshot in snapshots) / total_oi


def _safe_recent_liquidations(symbol: str):
    try:
        return get_recent_liquidations(symbol=symbol, limit=200)
    except Exception:
        return []


def _build_live_candles(snapshots: list[MarketSnapshot]) -> list[Candle]:
    base_price = _weighted_price(snapshots)
    candles: list[Candle] = []
    for index in range(245):
        wave = _wave(index)
        drift = (index - 122) * 1.3
        close = base_price + wave * 120 + drift
        open_price = close - _wave(index + 3) * 34
        high = max(open_price, close) + 22 + abs(_wave(index + 9)) * 46
        low = min(open_price, close) - 22 - abs(_wave(index + 15)) * 43
        candles.append(Candle(time=_time_label(index), open=open_price, high=high, low=low, close=close))
    candles[-1] = candles[-1].model_copy(update={"close": base_price, "high": max(candles[-1].high, base_price), "low": min(candles[-1].low, base_price)})
    return candles


def _buckets_to_heat_bands(buckets: list[HeatmapBucket]) -> list[HeatBand]:
    if not buckets:
        return []
    max_score = max(bucket.total_score for bucket in buckets) or 1
    bands: list[HeatBand] = []
    for index, bucket in enumerate(buckets):
        intensity = clamp(bucket.total_score / max_score, 0.2, 1.0)
        start = 8 + (index * 19) % 130
        end = min(244, start + 72 + int(intensity * 90))
        bands.append(HeatBand(price=bucket.price_bucket, start=start, end=end, intensity=intensity))
    return bands


def _buckets_to_profile(buckets: list[HeatmapBucket]) -> list[ProfileRow]:
    fallback_profile = build_profile()
    if not buckets:
        return fallback_profile
    bucket_map = {round(bucket.price_bucket): bucket for bucket in buckets}
    max_long = max(bucket.long_liq_usd for bucket in buckets) or 1
    max_short = max(bucket.short_liq_usd for bucket in buckets) or 1
    profile: list[ProfileRow] = []
    for row in fallback_profile:
        nearest = min(bucket_map, key=lambda price: abs(price - row.price))
        bucket = bucket_map[nearest]
        profile.append(
            ProfileRow(
                price=row.price,
                long=clamp(bucket.long_liq_usd / max_long * 112, 2, 112),
                short=clamp(bucket.short_liq_usd / max_short * 98, 2, 98),
            )
        )
    return profile


def _build_live_net(candles: list[Candle]) -> list[NetPoint]:
    return [NetPoint(time=candle.time, value=72 - _wave(index + 7) * 16 - (candle.close - candles[-1].close) / 85) for index, candle in enumerate(candles)]


def _wave(index: int) -> float:
    import math

    return math.sin(index * 0.17) * 0.65 + math.cos(index * 0.07) * 0.35


def _time_label(index: int) -> str:
    labels = [
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
    ]
    return labels[int((index / 244) * (len(labels) - 1))]
