from __future__ import annotations

import math
import time

from app.exchanges.base import MarketSnapshot
from app.models.schemas import ExchangeWeight, HeatmapBucket, LiquidationEvent
from app.services.mock_heatmap import clamp
from app.services.oi_delta_service import OIDeltaBucket

LEVERAGE_DISTRIBUTION = (
    (5, 0.10),
    (10, 0.20),
    (25, 0.30),
    (50, 0.25),
    (100, 0.15),
)
LIQUIDATION_BUFFER = 0.004
MAX_REASONABLE_BTCUSDT_OI_USD = 50_000_000_000
MIN_REASONABLE_BTCUSDT_OI_USD = 10_000
CONSUMED_EVENT_WINDOW_MS = 45 * 60 * 1000
BINANCE_WEIGHT_BIAS = 1.35
BINANCE_WEIGHT_CAP = 0.60
WEIGHTING_MODE = "oi_with_binance_bias"


def calculate_exchange_weights(snapshots: list[MarketSnapshot]) -> list[ExchangeWeight]:
    eligible = [snapshot for snapshot in snapshots if is_reasonable_open_interest_usd(snapshot)]
    weights_by_exchange = calculate_exchange_weight_map(eligible)
    if not weights_by_exchange:
        mock_weights = {"binance": 0.34, "bybit": 0.26, "okx": 0.18, "gate": 0.12, "mexc": 0.10}
        selected_total = sum(mock_weights.get(snapshot.exchange, 0.0) for snapshot in snapshots) or 1.0
        return [
            ExchangeWeight(
                exchange=snapshot.exchange,
                weight=mock_weights.get(snapshot.exchange, 0.0) / selected_total,
                open_interest_usd=snapshot.open_interest_usd,
            )
        for snapshot in snapshots
    ]
    return [
        ExchangeWeight(
            exchange=snapshot.exchange,
            weight=weights_by_exchange[snapshot.exchange],
            enabled=True,
            open_interest_usd=snapshot.open_interest_usd,
        )
        for snapshot in eligible
    ]


def calculate_exchange_weight_map(snapshots: list[MarketSnapshot]) -> dict[str, float]:
    eligible = [snapshot for snapshot in snapshots if is_reasonable_open_interest_usd(snapshot)]
    total_oi = sum(max(0.0, snapshot.open_interest_usd) for snapshot in eligible)
    if total_oi <= 0:
        return {}

    adjusted = {
        snapshot.exchange: (snapshot.open_interest_usd / total_oi) * _exchange_weight_bias(snapshot.exchange)
        for snapshot in eligible
    }
    normalized = _normalize_weights(adjusted)
    return _cap_binance_weight(normalized)


def is_reasonable_open_interest_usd(snapshot: MarketSnapshot) -> bool:
    value = snapshot.open_interest_usd
    if not math.isfinite(value):
        return False
    if value < MIN_REASONABLE_BTCUSDT_OI_USD or value > MAX_REASONABLE_BTCUSDT_OI_USD:
        return False
    if _is_finite_positive(snapshot.mark_price) and value < snapshot.mark_price * 0.01:
        return False
    return True


def exchange_weight_warnings(weights: list[ExchangeWeight]) -> list[str]:
    warnings: list[str] = []
    total = sum(weight.weight for weight in weights)
    total_oi = sum(
        weight.open_interest_usd
        for weight in weights
        if weight.open_interest_usd is not None and math.isfinite(weight.open_interest_usd) and weight.open_interest_usd > 0
    )
    if weights and abs(total - 1.0) > 0.001:
        warnings.append(f"exchange weights sum to {total:.4f}, expected 1.0")
    for weight in weights:
        if weight.weight >= 0.85 and len(weights) > 1:
            warnings.append(f"{weight.exchange} weight is unusually high at {weight.weight:.1%}; verify open_interest_usd unit")
        if total_oi > 0 and weight.open_interest_usd is not None and weight.open_interest_usd / total_oi >= 0.90 and len(weights) > 1:
            warnings.append(f"{weight.exchange} raw open_interest_usd share is unusually high at {weight.open_interest_usd / total_oi:.1%}; verify open_interest_usd unit")
    return warnings


def build_live_buckets(
    snapshots: list[MarketSnapshot],
    model: int,
    response_range: str,
    liquidation_events: list[LiquidationEvent] | None = None,
    historical_snapshots: list[MarketSnapshot] | None = None,
    oi_delta_buckets: list[OIDeltaBucket] | None = None,
) -> list[HeatmapBucket]:
    events = liquidation_events or []
    history = historical_snapshots or []
    delta_buckets = oi_delta_buckets or []
    if model == 1:
        return _apply_consumed_decay(_build_model_1(snapshots, response_range), events)
    if model == 2:
        return _apply_consumed_decay(_adjust_model_2(_build_model_1(snapshots, response_range), snapshots, history, response_range, delta_buckets), events)
    return _apply_consumed_decay(_adjust_model_3(_adjust_model_2(_build_model_1(snapshots, response_range), snapshots, history, response_range, delta_buckets), snapshots, events), events)


def _build_model_1(snapshots: list[MarketSnapshot], response_range: str) -> list[HeatmapBucket]:
    bucket_size = _bucket_size_for_range(response_range)
    raw: dict[float, dict[str, float]] = {}
    generated_at = int(time.time())
    eligible_snapshots = [snapshot for snapshot in snapshots if is_reasonable_open_interest_usd(snapshot)]
    working_snapshots = eligible_snapshots or [snapshot for snapshot in snapshots if _is_finite_positive(snapshot.mark_price)]
    weight_map = calculate_exchange_weight_map(eligible_snapshots)
    total_eligible_oi = sum(snapshot.open_interest_usd for snapshot in eligible_snapshots)

    for snapshot in working_snapshots:
        mark_price = _finite_positive(snapshot.mark_price)
        if mark_price <= 0:
            continue
        oi_usd = _snapshot_notional(snapshot, weight_map, total_eligible_oi)
        for leverage, share in LEVERAGE_DISTRIBUTION:
            notional = oi_usd * share
            long_price = mark_price * (1 - 1 / leverage + LIQUIDATION_BUFFER)
            short_price = mark_price * (1 + 1 / leverage - LIQUIDATION_BUFFER)
            long_bucket = _bucket_price(long_price, bucket_size)
            short_bucket = _bucket_price(short_price, bucket_size)
            raw.setdefault(long_bucket, {"long": 0.0, "short": 0.0})["long"] += notional * 0.52
            raw.setdefault(short_bucket, {"long": 0.0, "short": 0.0})["short"] += notional * 0.48

    max_total = max((value["long"] + value["short"] for value in raw.values()), default=1.0)
    confidence = _base_confidence(eligible_snapshots) if eligible_snapshots else min(_base_confidence(working_snapshots), 0.35)
    return [
        HeatmapBucket(
            ts=generated_at,
            price_bucket=price,
            long_liq_usd=value["long"],
            short_liq_usd=value["short"],
            total_score=clamp((value["long"] + value["short"]) / max_total, 0, 1),
            confidence=clamp(confidence, 0, 1),
            relative_intensity=clamp(((value["long"] + value["short"]) / max_total) * confidence, 0, 1),
            dominant_side=_dominant_side(value["long"], value["short"]),
            estimated_liq_usd=value["long"] + value["short"],
            consumed_score=0,
        )
        for price, value in sorted(raw.items())
    ]


def _adjust_model_2(
    buckets: list[HeatmapBucket],
    snapshots: list[MarketSnapshot] | None = None,
    historical_snapshots: list[MarketSnapshot] | None = None,
    response_range: str = "90d",
    oi_delta_buckets: list[OIDeltaBucket] | None = None,
) -> list[HeatmapBucket]:
    persisted_delta_adjusted = _apply_persisted_oi_delta_matrix(buckets, oi_delta_buckets or [], response_range)
    if persisted_delta_adjusted is not None:
        return persisted_delta_adjusted

    oi_delta_adjusted = _apply_oi_delta_adjustment(buckets, snapshots or [], historical_snapshots or [], response_range)
    if oi_delta_adjusted is not None:
        return oi_delta_adjusted

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
                relative_intensity=clamp(bucket.relative_intensity * factor, 0, 1),
                dominant_side=_dominant_side(bucket.long_liq_usd * factor, bucket.short_liq_usd * (2 - factor)),
                estimated_liq_usd=bucket.long_liq_usd * factor + bucket.short_liq_usd * (2 - factor),
                consumed_score=bucket.consumed_score,
            )
        )
    return adjusted


def _apply_persisted_oi_delta_matrix(
    buckets: list[HeatmapBucket],
    oi_delta_buckets: list[OIDeltaBucket],
    response_range: str,
) -> list[HeatmapBucket] | None:
    if not buckets or not oi_delta_buckets:
        return None

    now_ms = int(time.time() * 1000)
    lookback_ms = _range_lookback_ms(response_range)
    half_life_ms = max(60 * 60 * 1000, lookback_ms / 3)
    model_bucket_size = _bucket_size_for_range(response_range)
    boosts: dict[float, dict[str, float]] = {}
    used_delta = 0.0

    for delta in oi_delta_buckets:
        if delta.side not in {"long", "short"}:
            continue
        if not (_is_finite_positive(delta.oi_delta_usd) and math.isfinite(delta.score) and math.isfinite(delta.confidence)):
            continue
        age_ms = max(0, now_ms - delta.ts)
        if age_ms > lookback_ms:
            continue
        decay = 0.5 ** (age_ms / half_life_ms)
        weighted_delta = delta.oi_delta_usd * clamp(delta.score, 0, 1) * clamp(delta.confidence, 0, 1) * decay
        if weighted_delta <= 0:
            continue
        price = _bucket_price(delta.price_bucket, model_bucket_size)
        boosts.setdefault(price, {"long": 0.0, "short": 0.0, "consumed": 0.0})
        boosts[price][delta.side] += weighted_delta
        used_delta += weighted_delta

    if used_delta <= 0 or not boosts:
        return None

    merged: dict[float, dict[str, float]] = {
        bucket.price_bucket: {"long": bucket.long_liq_usd, "short": bucket.short_liq_usd, "consumed": bucket.consumed_score}
        for bucket in buckets
    }
    for price, boost in boosts.items():
        merged.setdefault(price, {"long": 0.0, "short": 0.0, "consumed": 0.0})
        # OI delta is an adjustment layer, not the full open interest estimate.
        merged[price]["long"] += boost["long"] * 0.74
        merged[price]["short"] += boost["short"] * 0.74

    max_total = max((value["long"] + value["short"] for value in merged.values()), default=1.0)
    base_confidence = max((bucket.confidence for bucket in buckets), default=0.5)
    delta_confidence = clamp(base_confidence + min(0.12, used_delta / 2_500_000_000), 0, 0.97)
    generated_at = buckets[0].ts
    return [
        HeatmapBucket(
            ts=generated_at,
            price_bucket=price,
            long_liq_usd=value["long"],
            short_liq_usd=value["short"],
            total_score=clamp((value["long"] + value["short"]) / max_total, 0, 1),
            confidence=delta_confidence,
            relative_intensity=clamp(((value["long"] + value["short"]) / max_total) * delta_confidence, 0, 1),
            dominant_side=_dominant_side(value["long"], value["short"]),
            estimated_liq_usd=value["long"] + value["short"],
            consumed_score=clamp(value.get("consumed", 0.0), 0, 1),
        )
        for price, value in sorted(merged.items())
    ]


def _apply_oi_delta_adjustment(
    buckets: list[HeatmapBucket],
    snapshots: list[MarketSnapshot],
    historical_snapshots: list[MarketSnapshot],
    response_range: str,
) -> list[HeatmapBucket] | None:
    if not buckets or not snapshots or not historical_snapshots:
        return None

    bucket_size = _bucket_size_for_range(response_range)
    boosts: dict[float, dict[str, float]] = {}
    used_delta = 0.0
    by_exchange: dict[str, list[MarketSnapshot]] = {}
    for historical in historical_snapshots:
        by_exchange.setdefault(historical.exchange, []).append(historical)

    for snapshot in snapshots:
        if not is_reasonable_open_interest_usd(snapshot):
            continue
        previous = _previous_snapshot(snapshot, by_exchange.get(snapshot.exchange, []))
        if previous is None or not _is_finite_positive(previous.open_interest_usd):
            continue
        delta_oi = snapshot.open_interest_usd - previous.open_interest_usd
        if delta_oi <= max(snapshot.open_interest_usd * 0.002, 50_000):
            continue
        delta_oi = min(delta_oi, snapshot.open_interest_usd * 0.22)
        price_change = snapshot.mark_price - previous.mark_price
        direction = "long" if price_change >= 0 else "short"
        used_delta += delta_oi
        for leverage, share in LEVERAGE_DISTRIBUTION:
            notional = delta_oi * share
            if direction == "long":
                price = snapshot.mark_price * (1 - 1 / leverage + LIQUIDATION_BUFFER)
                bucket_price = _bucket_price(price, bucket_size)
                boosts.setdefault(bucket_price, {"long": 0.0, "short": 0.0})["long"] += notional * 0.62
            else:
                price = snapshot.mark_price * (1 + 1 / leverage - LIQUIDATION_BUFFER)
                bucket_price = _bucket_price(price, bucket_size)
                boosts.setdefault(bucket_price, {"long": 0.0, "short": 0.0})["short"] += notional * 0.58

    if used_delta <= 0 or not boosts:
        return None

    merged: dict[float, dict[str, float]] = {
        bucket.price_bucket: {"long": bucket.long_liq_usd, "short": bucket.short_liq_usd, "consumed": bucket.consumed_score}
        for bucket in buckets
    }
    for price, boost in boosts.items():
        merged.setdefault(price, {"long": 0.0, "short": 0.0, "consumed": 0.0})
        merged[price]["long"] += boost["long"]
        merged[price]["short"] += boost["short"]

    max_total = max((value["long"] + value["short"] for value in merged.values()), default=1.0)
    base_confidence = max((bucket.confidence for bucket in buckets), default=0.5)
    delta_confidence = clamp(base_confidence + min(0.08, used_delta / 2_000_000_000), 0, 0.96)
    generated_at = buckets[0].ts
    return [
        HeatmapBucket(
            ts=generated_at,
            price_bucket=price,
            long_liq_usd=value["long"],
            short_liq_usd=value["short"],
            total_score=clamp((value["long"] + value["short"]) / max_total, 0, 1),
            confidence=delta_confidence,
            relative_intensity=clamp(((value["long"] + value["short"]) / max_total) * delta_confidence, 0, 1),
            dominant_side=_dominant_side(value["long"], value["short"]),
            estimated_liq_usd=value["long"] + value["short"],
            consumed_score=clamp(value.get("consumed", 0.0), 0, 1),
        )
        for price, value in sorted(merged.items())
    ]


def _previous_snapshot(snapshot: MarketSnapshot, candidates: list[MarketSnapshot]) -> MarketSnapshot | None:
    older = [
        candidate
        for candidate in candidates
        if candidate.ts < snapshot.ts
        and _is_finite_positive(candidate.mark_price)
        and _is_finite_positive(candidate.open_interest_usd)
        and candidate.open_interest_usd <= MAX_REASONABLE_BTCUSDT_OI_USD
    ]
    if not older:
        return None
    return max(older, key=lambda candidate: candidate.ts)


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
            relative_intensity=clamp(bucket.relative_intensity + event_scores.get(bucket.price_bucket, 0.0) * 0.07, 0, 1),
            dominant_side=_dominant_side(bucket.long_liq_usd * long_factor, bucket.short_liq_usd * short_factor),
            estimated_liq_usd=bucket.long_liq_usd * long_factor + bucket.short_liq_usd * short_factor,
            consumed_score=bucket.consumed_score,
        )
        for bucket in buckets
    ]


def _apply_consumed_decay(buckets: list[HeatmapBucket], liquidation_events: list[LiquidationEvent]) -> list[HeatmapBucket]:
    if not buckets or not liquidation_events:
        return buckets
    consumed = _consumed_scores(buckets, liquidation_events)
    if not consumed:
        return buckets
    decayed: list[HeatmapBucket] = []
    for bucket in buckets:
        long_consumed = consumed.get((bucket.price_bucket, "long_liquidated"), 0.0)
        short_consumed = consumed.get((bucket.price_bucket, "short_liquidated"), 0.0)
        long_factor = 1.0 - min(0.68, long_consumed * 0.58)
        short_factor = 1.0 - min(0.68, short_consumed * 0.58)
        long_liq_usd = bucket.long_liq_usd * long_factor
        short_liq_usd = bucket.short_liq_usd * short_factor
        consumed_score = clamp(max(long_consumed, short_consumed, bucket.consumed_score), 0, 1)
        total_factor = 1.0 - consumed_score * 0.36
        decayed.append(
            HeatmapBucket(
                ts=bucket.ts,
                price_bucket=bucket.price_bucket,
                long_liq_usd=long_liq_usd,
                short_liq_usd=short_liq_usd,
                total_score=clamp(bucket.total_score * total_factor, 0, 1),
                confidence=bucket.confidence,
                relative_intensity=clamp(bucket.relative_intensity * total_factor, 0, 1),
                dominant_side=_dominant_side(long_liq_usd, short_liq_usd),
                estimated_liq_usd=long_liq_usd + short_liq_usd,
                consumed_score=consumed_score,
            )
        )
    return decayed


def _consumed_scores(buckets: list[HeatmapBucket], liquidation_events: list[LiquidationEvent]) -> dict[tuple[float, str], float]:
    bucket_prices = [bucket.price_bucket for bucket in buckets]
    now_ms = int(time.time() * 1000)
    max_event_notional = max((event.notional_usd for event in liquidation_events if event.notional_usd > 0), default=1.0)
    scores: dict[tuple[float, str], float] = {}
    for event in liquidation_events:
        if event.side not in {"long_liquidated", "short_liquidated"}:
            continue
        age_ms = max(0, now_ms - event.ts)
        if age_ms > CONSUMED_EVENT_WINDOW_MS:
            continue
        nearest = min(bucket_prices, key=lambda price: abs(price - event.price))
        recency = 1.0 - age_ms / CONSUMED_EVENT_WINDOW_MS
        notional_score = min(event.notional_usd / max_event_notional, 1.0)
        score = clamp(0.22 + recency * 0.48 + notional_score * 0.30, 0, 1)
        key = (nearest, event.side)
        scores[key] = clamp(scores.get(key, 0.0) + score * 0.72, 0, 1)
    return scores


def _bucket_price(price: float, bucket_size: int) -> float:
    return round(price / bucket_size) * bucket_size


def _bucket_size_for_range(response_range: str) -> int:
    normalized = response_range.lower()
    if normalized in {"12h", "24h"}:
        return 100
    if normalized in {"3d", "7d", "30d"}:
        return 250
    return 500


def _range_lookback_ms(response_range: str) -> int:
    normalized = response_range.lower()
    hours_by_range = {
        "12h": 12,
        "24h": 24,
        "3d": 72,
        "7d": 168,
        "30d": 720,
        "90d": 2160,
        "180d": 4320,
        "1y": 8760,
    }
    return hours_by_range.get(normalized, 2160) * 60 * 60 * 1000


def _snapshot_notional(snapshot: MarketSnapshot, weight_map: dict[str, float] | None = None, total_eligible_oi: float = 0.0) -> float:
    if weight_map and snapshot.exchange in weight_map and total_eligible_oi > 0:
        return total_eligible_oi * weight_map[snapshot.exchange]
    if is_reasonable_open_interest_usd(snapshot):
        return snapshot.open_interest_usd
    # If an exchange reports OI in contracts or an already-notional unit, a
    # second mark-price multiplication can create trillion-dollar clusters.
    # Use a tiny placeholder only when all usable OI is unavailable.
    return max(_finite_positive(snapshot.mark_price), 1.0) * 100


def _dominant_side(long_liq_usd: float, short_liq_usd: float) -> str:
    total = long_liq_usd + short_liq_usd
    if total <= 0:
        return "balanced"
    if long_liq_usd / total >= 0.58:
        return "long"
    if short_liq_usd / total >= 0.58:
        return "short"
    return "balanced"


def _finite_positive(value: float) -> float:
    return value if _is_finite_positive(value) else 0.0


def _is_finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


def _exchange_weight_bias(exchange: str) -> float:
    return BINANCE_WEIGHT_BIAS if exchange.lower() == "binance" else 1.0


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(value for value in weights.values() if math.isfinite(value) and value > 0)
    if total <= 0:
        return {}
    return {exchange: max(0.0, value) / total for exchange, value in weights.items() if math.isfinite(value) and value > 0}


def _cap_binance_weight(weights: dict[str, float]) -> dict[str, float]:
    binance_weight = weights.get("binance")
    if binance_weight is None or binance_weight <= BINANCE_WEIGHT_CAP:
        return weights

    other_total = sum(weight for exchange, weight in weights.items() if exchange != "binance")
    capped = {"binance": BINANCE_WEIGHT_CAP}
    remaining = 1.0 - BINANCE_WEIGHT_CAP
    if other_total <= 0:
        return {"binance": 1.0}

    for exchange, weight in weights.items():
        if exchange == "binance":
            continue
        capped[exchange] = remaining * (weight / other_total)
    return capped


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
