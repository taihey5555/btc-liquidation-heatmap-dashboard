from __future__ import annotations

import time

from app.exchanges.base import MarketSnapshot
from app.models.schemas import ExchangeWeight, HeatmapBucket, LiquidationEvent
from app.services.mock_heatmap import clamp

LEVERAGE_DISTRIBUTION = (
    (5, 0.10),
    (10, 0.20),
    (25, 0.30),
    (50, 0.25),
    (100, 0.15),
)
LIQUIDATION_BUFFER = 0.004


def calculate_exchange_weights(snapshots: list[MarketSnapshot]) -> list[ExchangeWeight]:
    eligible = [snapshot for snapshot in snapshots if snapshot.open_interest_usd > 0]
    total_oi = sum(max(0.0, snapshot.open_interest_usd) for snapshot in eligible)
    if total_oi <= 0:
        mock_weights = {"binance": 0.34, "bybit": 0.26, "okx": 0.18, "gate": 0.12, "mexc": 0.10}
        return [
            ExchangeWeight(exchange=snapshot.exchange, weight=mock_weights.get(snapshot.exchange, 0.0), open_interest_usd=snapshot.open_interest_usd)
            for snapshot in snapshots
        ]
    return [
        ExchangeWeight(
            exchange=snapshot.exchange,
            weight=snapshot.open_interest_usd / total_oi,
            enabled=True,
            open_interest_usd=snapshot.open_interest_usd,
        )
        for snapshot in eligible
    ]


def build_live_buckets(
    snapshots: list[MarketSnapshot],
    model: int,
    response_range: str,
    liquidation_events: list[LiquidationEvent] | None = None,
) -> list[HeatmapBucket]:
    if model == 1:
        return _build_model_1(snapshots, response_range)
    if model == 2:
        return _adjust_model_2(_build_model_1(snapshots, response_range))
    return _adjust_model_3(_adjust_model_2(_build_model_1(snapshots, response_range)), snapshots, liquidation_events or [])


def _build_model_1(snapshots: list[MarketSnapshot], response_range: str) -> list[HeatmapBucket]:
    bucket_size = 100 if response_range.lower() in {"24h", "7d"} else 250
    raw: dict[float, dict[str, float]] = {}
    generated_at = int(time.time())

    for snapshot in snapshots:
        oi_usd = max(0.0, snapshot.open_interest_usd)
        for leverage, share in LEVERAGE_DISTRIBUTION:
            notional = oi_usd * share
            long_price = snapshot.mark_price * (1 - 1 / leverage + LIQUIDATION_BUFFER)
            short_price = snapshot.mark_price * (1 + 1 / leverage - LIQUIDATION_BUFFER)
            long_bucket = _bucket_price(long_price, bucket_size)
            short_bucket = _bucket_price(short_price, bucket_size)
            raw.setdefault(long_bucket, {"long": 0.0, "short": 0.0})["long"] += notional * 0.52
            raw.setdefault(short_bucket, {"long": 0.0, "short": 0.0})["short"] += notional * 0.48

    max_total = max((value["long"] + value["short"] for value in raw.values()), default=1.0)
    confidence = _base_confidence(snapshots)
    return [
        HeatmapBucket(
            ts=generated_at,
            price_bucket=price,
            long_liq_usd=value["long"],
            short_liq_usd=value["short"],
            total_score=(value["long"] + value["short"]) / max_total,
            confidence=confidence,
        )
        for price, value in sorted(raw.items())
    ]


def _adjust_model_2(buckets: list[HeatmapBucket]) -> list[HeatmapBucket]:
    adjusted: list[HeatmapBucket] = []
    for index, bucket in enumerate(buckets):
        factor = 1.0 + (0.04 if index % 2 == 0 else -0.03)
        adjusted.append(
            HeatmapBucket(
                ts=bucket.ts,
                price_bucket=bucket.price_bucket,
                long_liq_usd=bucket.long_liq_usd * factor,
                short_liq_usd=bucket.short_liq_usd * (2 - factor),
                total_score=clamp(bucket.total_score * factor, 0, 1),
                confidence=clamp(bucket.confidence - 0.03, 0, 1),
            )
        )
    return adjusted


def _adjust_model_3(buckets: list[HeatmapBucket], snapshots: list[MarketSnapshot], liquidation_events: list[LiquidationEvent]) -> list[HeatmapBucket]:
    avg_funding = sum(snapshot.funding_rate for snapshot in snapshots) / max(1, len(snapshots))
    long_factor = 0.96 if avg_funding > 0 else 1.04
    short_factor = 1.04 if avg_funding > 0 else 0.96
    event_scores = _event_activity_scores(buckets, liquidation_events)
    return [
        HeatmapBucket(
            ts=bucket.ts,
            price_bucket=bucket.price_bucket,
            long_liq_usd=bucket.long_liq_usd * long_factor,
            short_liq_usd=bucket.short_liq_usd * short_factor,
            total_score=clamp(bucket.total_score + event_scores.get(bucket.price_bucket, 0.0) * 0.08, 0, 1),
            confidence=clamp(bucket.confidence + 0.02 + event_scores.get(bucket.price_bucket, 0.0) * 0.10, 0, 1),
        )
        for bucket in buckets
    ]


def _bucket_price(price: float, bucket_size: int) -> float:
    return round(price / bucket_size) * bucket_size


def _base_confidence(snapshots: list[MarketSnapshot]) -> float:
    if not snapshots:
        return 0.0
    exchange_score = min(len(snapshots) / 5, 1.0)
    oi_coverage = sum(1 for snapshot in snapshots if snapshot.open_interest_usd > 0) / len(snapshots)
    now_ms = int(time.time() * 1000)
    newest = max(snapshot.ts for snapshot in snapshots)
    freshness_score = 1.0 if now_ms - newest < 30_000 else 0.82 if now_ms - newest < 180_000 else 0.65
    return clamp(0.45 + exchange_score * 0.22 + oi_coverage * 0.2 + freshness_score * 0.13, 0, 0.95)


def _event_activity_scores(buckets: list[HeatmapBucket], liquidation_events: list[LiquidationEvent]) -> dict[float, float]:
    if not buckets or not liquidation_events:
        return {}
    bucket_prices = [bucket.price_bucket for bucket in buckets]
    raw_scores = {price: 0.0 for price in bucket_prices}
    max_notional = max((event.notional_usd for event in liquidation_events), default=1.0) or 1.0
    for event in liquidation_events:
        nearest = min(bucket_prices, key=lambda price: abs(price - event.price))
        # Executed liquidations are historical activity, not future liquidation
        # levels, so this is deliberately a small confidence/activity nudge.
        raw_scores[nearest] += min(event.notional_usd / max_notional, 1.0)
    max_score = max(raw_scores.values(), default=1.0) or 1.0
    return {price: score / max_score for price, score in raw_scores.items() if score > 0}
