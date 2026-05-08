from __future__ import annotations

from app.models.schemas import HeatmapBucket, LiquidationSignalResponse, SignalZone, TopClustersResponse, TopClusterZone
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


async def get_top_clusters_signal(
    symbol: str,
    model: int,
    ranges: list[str],
    source: str = "live",
    exchanges: list[str] | None = None,
    limit: int = 10,
    min_intensity: float = 0.2,
) -> TopClustersResponse:
    normalized_ranges = [item.lower() for item in ranges] or ["24h", "3d"]
    top_clusters: list[TopClusterZone] = []
    nearest_longs: list[TopClusterZone] = []
    nearest_shorts: list[TopClusterZone] = []
    warnings: list[str] = []
    exchanges_used: list[str] = []
    fallback = False
    response_source = source
    current_price = 0.0
    generated_at: int | None = None
    freshness_values: list[int] = []

    for response_range in normalized_ranges:
        heatmap = await get_heatmap(symbol=symbol, model=model, currency="USD", response_range=response_range, source=source, exchanges=exchanges)
        current_price = heatmap.current_price or heatmap.last_price_usd or current_price
        generated_at = max(generated_at or 0, heatmap.generated_at or 0) or None
        if heatmap.data_freshness_ms is not None:
            freshness_values.append(heatmap.data_freshness_ms)
        response_source = heatmap.source
        fallback = fallback or heatmap.fallback
        exchanges_used = sorted(set([*exchanges_used, *heatmap.exchanges_used]))
        warnings.extend(heatmap.warnings + heatmap.excluded_exchanges)

        buckets = [bucket for bucket in heatmap.buckets if bucket.relative_intensity >= min_intensity]
        top_clusters.extend(
            _top_zone_from_bucket(bucket, current_price, bucket.dominant_side, response_range, heatmap.model)
            for bucket in buckets
        )
        nearest_longs.extend(
            _top_zone_from_bucket(bucket, current_price, "long", response_range, heatmap.model)
            for bucket in buckets
            if bucket.price_bucket < current_price and bucket.long_liq_usd > 0
        )
        nearest_shorts.extend(
            _top_zone_from_bucket(bucket, current_price, "short", response_range, heatmap.model)
            for bucket in buckets
            if bucket.price_bucket > current_price and bucket.short_liq_usd > 0
        )

    return TopClustersResponse(
        symbol=symbol.upper(),
        source=response_source,
        fallback=fallback,
        current_price=current_price,
        generated_at=generated_at,
        data_freshness_ms=max(freshness_values) if freshness_values else None,
        ranges=normalized_ranges,
        exchanges_used=exchanges_used,
        warnings=_unique(warnings),
        top_clusters=sorted(top_clusters, key=lambda zone: zone.relative_intensity, reverse=True)[:limit],
        nearest_long_liq_below=sorted(nearest_longs, key=lambda zone: (abs(zone.distance_pct), -zone.relative_intensity))[:limit],
        nearest_short_liq_above=sorted(nearest_shorts, key=lambda zone: (abs(zone.distance_pct), -zone.relative_intensity))[:limit],
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


def _top_zone_from_bucket(bucket: HeatmapBucket, current_price: float, side: str, response_range: str, model: int) -> TopClusterZone:
    distance_pct = ((bucket.price_bucket - current_price) / current_price) * 100 if current_price else 0.0
    return TopClusterZone(
        range=response_range,
        model=model,
        price=bucket.price_bucket,
        side=side,
        distance_pct=distance_pct,
        relative_intensity=bucket.relative_intensity,
        confidence=bucket.confidence,
        consumed_score=bucket.consumed_score,
        total_score=bucket.total_score,
        estimated_liq_usd=bucket.estimated_liq_usd,
    )


def _unique(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_messages: list[str] = []
    for message in messages:
        if message and message not in seen:
            seen.add(message)
            unique_messages.append(message)
    return unique_messages
