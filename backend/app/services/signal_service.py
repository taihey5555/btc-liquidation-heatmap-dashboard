from __future__ import annotations

from app.models.schemas import HeatmapBucket, LiquidationSignalResponse, SignalZone
from app.services.heatmap_service import get_heatmap


async def get_liquidation_zones_signal(
    symbol: str,
    model: int,
    response_range: str,
    source: str = "live",
    exchanges: list[str] | None = None,
    limit: int = 5,
    min_intensity: float = 0.2,
) -> LiquidationSignalResponse:
    heatmap = await get_heatmap(symbol=symbol, model=model, currency="USD", response_range=response_range, source=source, exchanges=exchanges)
    current_price = heatmap.current_price or heatmap.last_price_usd
    buckets = [bucket for bucket in heatmap.buckets if bucket.relative_intensity >= min_intensity]

    long_below = sorted(
        (
            _zone_from_bucket(bucket, current_price, "long")
            for bucket in buckets
            if bucket.price_bucket < current_price and bucket.long_liq_usd > 0
        ),
        key=lambda zone: (abs(zone.distance_pct), -zone.relative_intensity),
    )[:limit]

    short_above = sorted(
        (
            _zone_from_bucket(bucket, current_price, "short")
            for bucket in buckets
            if bucket.price_bucket > current_price and bucket.short_liq_usd > 0
        ),
        key=lambda zone: (abs(zone.distance_pct), -zone.relative_intensity),
    )[:limit]

    strongest = sorted(
        (_zone_from_bucket(bucket, current_price, bucket.dominant_side) for bucket in buckets),
        key=lambda zone: zone.relative_intensity,
        reverse=True,
    )[:limit]

    return LiquidationSignalResponse(
        symbol=heatmap.symbol,
        model=heatmap.model,
        range=heatmap.range,
        source=heatmap.source,
        fallback=heatmap.fallback,
        current_price=current_price,
        generated_at=heatmap.generated_at,
        data_freshness_ms=heatmap.data_freshness_ms,
        exchanges_used=heatmap.exchanges_used,
        warnings=heatmap.warnings + heatmap.excluded_exchanges,
        nearest_long_liq_below=long_below,
        nearest_short_liq_above=short_above,
        strongest_clusters=strongest,
    )


def _zone_from_bucket(bucket: HeatmapBucket, current_price: float, side: str) -> SignalZone:
    distance_pct = ((bucket.price_bucket - current_price) / current_price) * 100 if current_price else 0.0
    return SignalZone(
        price=bucket.price_bucket,
        side=side,
        distance_pct=distance_pct,
        relative_intensity=bucket.relative_intensity,
        confidence=bucket.confidence,
        consumed_score=bucket.consumed_score,
        total_score=bucket.total_score,
        estimated_liq_usd=bucket.estimated_liq_usd,
    )
