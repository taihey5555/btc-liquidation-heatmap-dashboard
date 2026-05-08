from __future__ import annotations

from datetime import UTC, datetime

from app.exchanges.base import CandleSnapshot, MarketSnapshot
from app.config import get_settings
from app.models.schemas import Candle, HeatBand, HeatmapBucket, HeatmapResponse, NetPoint, ProfileRow
from app.services.collector import collect_market_data
from app.services.liquidation_models import (
    BINANCE_WEIGHT_BIAS,
    BINANCE_WEIGHT_CAP,
    WEIGHTING_MODE,
    build_live_buckets,
    calculate_exchange_weights,
    exchange_weight_warnings,
)
from app.services.liquidation_streams import get_recent_liquidations
from app.services.market_history import get_latest_market_snapshot, get_recent_market_snapshots
from app.services.mock_heatmap import FX_USD_JPY, build_mock_heatmap, build_profile, clamp
from app.services.oi_delta_service import get_recent_oi_delta_buckets

DEFAULT_PRICE_MIN = 75000
DEFAULT_PRICE_MAX = 81950


async def get_heatmap(
    symbol: str,
    model: int,
    currency: str,
    response_range: str,
    source: str = "mock",
    exchanges: list[str] | None = None,
) -> HeatmapResponse:
    normalized_source = source.lower()
    if normalized_source == "mock":
        return build_mock_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range)
    return await get_live_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range, exchanges=exchanges)


async def get_live_heatmap(symbol: str, model: int, currency: str, response_range: str, exchanges: list[str] | None = None) -> HeatmapResponse:
    collector_result = await collect_market_data(symbol, exchange_names=exchanges)
    if not collector_result.snapshots:
        reference_price, reference_source = _latest_reference_price(symbol)
        fallback = build_mock_heatmap(
            symbol=symbol,
            model=model,
            currency=currency,
            response_range=response_range,
            reference_price=reference_price,
            current_price_source=reference_source,
        )
        fallback.source = "mock"
        fallback.fallback = True
        fallback.warnings = collector_result.warnings or ["live source unavailable; mock fallback used"]
        fallback.exchanges_used = []
        fallback.excluded_exchanges = _excluded_exchanges([], exchanges, collector_result.warnings, [])
        fallback.generated_at = int(datetime.now(UTC).timestamp())
        fallback.data_freshness_ms = None
        fallback.current_price = fallback.last_price_usd
        return fallback

    snapshots = collector_result.snapshots
    recent_liquidations = _safe_recent_liquidations(symbol)
    historical_snapshots = _safe_recent_market_snapshots(symbol, response_range)
    oi_delta_buckets = _safe_recent_oi_delta_buckets(symbol, response_range)
    buckets = build_live_buckets(
        snapshots=snapshots,
        model=model,
        response_range=response_range,
        liquidation_events=recent_liquidations,
        historical_snapshots=historical_snapshots,
        oi_delta_buckets=oi_delta_buckets,
    )
    candles = _build_live_candles(snapshots, collector_result.candles)
    last_price, current_price_source = _weighted_price(snapshots)
    normalized_currency = currency.upper()
    display_price = f"${last_price:,.0f}" if normalized_currency == "USD" else f"¥{last_price * FX_USD_JPY:,.0f}"
    exchange_weights = calculate_exchange_weights(snapshots)
    warnings = [*collector_result.warnings, *exchange_weight_warnings(exchange_weights)]
    excluded_exchanges = _excluded_exchanges(snapshots, exchanges, collector_result.warnings, exchange_weights)
    return HeatmapResponse(
        symbol=symbol.upper(),
        model=model,
        currency=normalized_currency,
        range=response_range,
        source="live",
        fallback=False,
        exchanges_used=collector_result.exchanges_used,
        excluded_exchanges=excluded_exchanges,
        generated_at=int(datetime.now(UTC).timestamp()),
        warnings=warnings,
        data_freshness_ms=collector_result.data_freshness_ms,
        current_price=last_price,
        current_price_source=current_price_source,
        weighting_mode=WEIGHTING_MODE,
        weight_biases={"binance": BINANCE_WEIGHT_BIAS},
        weight_caps={"binance": BINANCE_WEIGHT_CAP},
        display_price=display_price,
        last_price_usd=last_price,
        fx_usd_jpy=FX_USD_JPY,
        candles=candles,
        heat_bands=_buckets_to_heat_bands(buckets),
        profile=_buckets_to_profile(buckets),
        net=_build_live_net(candles),
        buckets=buckets,
        exchange_weights=exchange_weights,
    )


def _weighted_price(snapshots: list[MarketSnapshot]) -> tuple[float, str]:
    total_oi = sum(max(0.0, snapshot.open_interest_usd) for snapshot in snapshots)
    if total_oi <= 0:
        source_counts: dict[str, int] = {}
        prices = []
        for snapshot in snapshots:
            price, source = _snapshot_current_price(snapshot)
            prices.append(price)
            source_counts[source] = source_counts.get(source, 0) + 1
        source = max(source_counts, key=source_counts.get)
        return sum(prices) / len(prices), f"equal-weighted {source}"
    source_weights: dict[str, float] = {}
    weighted_price = 0.0
    for snapshot in snapshots:
        price, source = _snapshot_current_price(snapshot)
        weight = max(0.0, snapshot.open_interest_usd)
        weighted_price += price * weight
        source_weights[source] = source_weights.get(source, 0.0) + weight
    source = max(source_weights, key=source_weights.get)
    return weighted_price / total_oi, f"oi-weighted {source}"


def _snapshot_current_price(snapshot: MarketSnapshot) -> tuple[float, str]:
    if snapshot.mark_price > 0:
        return snapshot.mark_price, "mark_price"
    if snapshot.last_price > 0:
        return snapshot.last_price, "last_price"
    if snapshot.index_price > 0:
        return snapshot.index_price, "index_price"
    return 0.0, "missing_price"


def _safe_recent_liquidations(symbol: str):
    try:
        return get_recent_liquidations(symbol=symbol, limit=200)
    except Exception:
        return []


def _safe_recent_market_snapshots(symbol: str, response_range: str) -> list[MarketSnapshot]:
    try:
        return get_recent_market_snapshots(symbol=symbol, lookback_ms=_history_lookback_ms(response_range))
    except Exception:
        return []


def _safe_recent_oi_delta_buckets(symbol: str, response_range: str):
    try:
        return get_recent_oi_delta_buckets(symbol=symbol, lookback_ms=_delta_lookback_ms(response_range))
    except Exception:
        return []


def _latest_reference_price(symbol: str) -> tuple[float | None, str]:
    try:
        snapshot = get_latest_market_snapshot(symbol)
    except Exception:
        return None, "mock fallback"
    if snapshot is None:
        return None, "mock fallback"
    price, source = _snapshot_current_price(snapshot)
    if price <= 0:
        return None, "mock fallback"
    return price, f"mock fallback anchored to last {snapshot.exchange} {source}"


def _history_lookback_ms(response_range: str) -> int:
    normalized = response_range.lower()
    if normalized in {"12h", "24h"}:
        return 6 * 60 * 60 * 1000
    if normalized in {"3d", "7d"}:
        return 24 * 60 * 60 * 1000
    return 72 * 60 * 60 * 1000


def _delta_lookback_ms(response_range: str) -> int:
    normalized = response_range.lower()
    if normalized == "12h":
        return 12 * 60 * 60 * 1000
    if normalized == "24h":
        return 24 * 60 * 60 * 1000
    if normalized == "3d":
        return 3 * 24 * 60 * 60 * 1000
    if normalized == "7d":
        return 7 * 24 * 60 * 60 * 1000
    if normalized == "30d":
        return 30 * 24 * 60 * 60 * 1000
    if normalized == "180d":
        return 180 * 24 * 60 * 60 * 1000
    if normalized == "1y":
        return 365 * 24 * 60 * 60 * 1000
    return 90 * 24 * 60 * 60 * 1000


def _build_live_candles(snapshots: list[MarketSnapshot], live_candles: list[CandleSnapshot] | None = None) -> list[Candle]:
    if live_candles:
        return _candles_from_klines(live_candles)
    weighted_price, _source = _weighted_price(snapshots)
    base_price = weighted_price if weighted_price > 0 else 78_000
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


def _candles_from_klines(live_candles: list[CandleSnapshot]) -> list[Candle]:
    selected = live_candles[-245:]
    if not selected:
        return []
    labels = _range_labels(len(selected))
    return [
        Candle(
            time=labels[index],
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
        )
        for index, candle in enumerate(selected)
    ]


def _range_labels(count: int) -> list[str]:
    if count <= 1:
        return ["now"]
    return [_time_label(int((index / max(1, count - 1)) * 244)) for index in range(count)]


def _buckets_to_heat_bands(buckets: list[HeatmapBucket]) -> list[HeatBand]:
    if not buckets:
        return []
    max_signal = max(max(bucket.relative_intensity, bucket.total_score * bucket.confidence) for bucket in buckets) or 1
    bands: list[HeatBand] = []
    for index, bucket in enumerate(buckets):
        signal = max(bucket.relative_intensity, bucket.total_score * bucket.confidence)
        intensity = clamp(signal / max_signal, 0.08, 1.0)
        for layer in range(10):
            layer_intensity = clamp((intensity ** 1.28) * (1.0 - layer * 0.048), 0.035, 1.0)
            start = 4 + (index * 13 + layer * 19) % 188
            end = min(244, start + 34 + int(layer_intensity * 112) + (layer % 4) * 11)
            price_offset = (layer - 4.5) * 13
            bands.append(
                HeatBand(
                    price=bucket.price_bucket + price_offset,
                    start=start,
                    end=end,
                    intensity=layer_intensity,
                )
            )
    return bands


def _excluded_exchanges(
    snapshots: list[MarketSnapshot],
    requested_exchanges: list[str] | None,
    warnings: list[str],
    exchange_weights,
) -> list[str]:
    requested = [name.lower() for name in (requested_exchanges or list(get_settings().enabled_exchanges))]
    successful = {snapshot.exchange for snapshot in snapshots}
    weighted = {weight.exchange for weight in exchange_weights}
    warning_by_exchange: dict[str, str] = {}
    for warning in warnings:
        exchange, _, reason = warning.partition(":")
        if exchange:
            warning_by_exchange[exchange.strip().lower()] = reason.strip() or warning

    excluded: list[str] = []
    for exchange in requested:
        if exchange not in successful:
            reason = warning_by_exchange.get(exchange, "no live snapshot")
            excluded.append(f"{exchange}: {reason}")
        elif exchange not in weighted:
            excluded.append(f"{exchange}: excluded from weights; open_interest_usd unavailable or outside guard")
    return excluded


def _buckets_to_profile(buckets: list[HeatmapBucket]) -> list[ProfileRow]:
    if not buckets:
        return build_profile()
    bucket_map = {round(bucket.price_bucket): bucket for bucket in buckets}
    max_long = max(bucket.long_liq_usd for bucket in buckets) or 1
    max_short = max(bucket.short_liq_usd for bucket in buckets) or 1
    min_price = min(bucket.price_bucket for bucket in buckets)
    max_price = max(bucket.price_bucket for bucket in buckets)
    span = max(max_price - min_price, 6_000)
    lower = min_price - span * 0.05
    upper = max_price + span * 0.05
    profile: list[ProfileRow] = []
    for index in range(96):
        price = lower + (index / 95) * (upper - lower)
        nearest = min(bucket_map, key=lambda bucket_price: abs(bucket_price - price))
        bucket = bucket_map[nearest]
        profile.append(
            ProfileRow(
                price=price,
                long=clamp((bucket.long_liq_usd / max_long) ** 1.35 * 112, 0.4, 112),
                short=clamp((bucket.short_liq_usd / max_short) ** 1.35 * 98, 0.4, 98),
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
