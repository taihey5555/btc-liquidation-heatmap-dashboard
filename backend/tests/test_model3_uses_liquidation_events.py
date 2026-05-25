import time

from app.exchanges.base import MarketSnapshot
from app.models.schemas import LiquidationEvent
from app.services.liquidation_models import build_live_buckets


def test_model3_uses_liquidation_events() -> None:
    snapshot = MarketSnapshot("binance", "BTCUSDT", 1, 82000, 82000, 100, 8_200_000, 0.0001, 1000, 82000, None, {})
    without_events = build_live_buckets([snapshot], model=3, response_range="90d", liquidation_events=[])
    with_events = build_live_buckets(
        [snapshot],
        model=3,
        response_range="90d",
        liquidation_events=[
            LiquidationEvent(
                exchange="binance",
                symbol="BTCUSDT",
                ts=1760000000000,
                side="long_liquidated",
                price=78750,
                quantity=1,
                notional_usd=78_750,
            )
        ],
    )

    assert max(bucket.confidence for bucket in with_events) > max(bucket.confidence for bucket in without_events)


def test_liquidation_event_consumes_matching_cluster() -> None:
    now_ms = int(time.time() * 1000)
    snapshot = MarketSnapshot("binance", "BTCUSDT", 1760000000000, 82000, 82000, 100, 8_200_000_000, 0.0001, 1000, 82000, None, {})
    without_events = build_live_buckets([snapshot], model=1, response_range="90d", liquidation_events=[])
    with_events = build_live_buckets(
        [snapshot],
        model=1,
        response_range="90d",
        liquidation_events=[
            LiquidationEvent(
                exchange="binance",
                symbol="BTCUSDT",
                ts=now_ms,
                side="long_liquidated",
                price=79000,
                quantity=4,
                notional_usd=316_000,
            )
        ],
    )

    before = min(without_events, key=lambda bucket: abs(bucket.price_bucket - 79000))
    after = min(with_events, key=lambda bucket: abs(bucket.price_bucket - 79000))

    assert after.consumed_score > 0
    assert after.long_liq_usd < before.long_liq_usd
    assert after.relative_intensity < before.relative_intensity
    assert after.recent_liq_event_count == 1
    assert after.recent_liq_notional_usd == 316_000
    assert after.last_liq_event_ts == now_ms


def test_liquidation_event_consumption_is_side_and_distance_scoped() -> None:
    now_ms = int(time.time() * 1000)
    snapshot = MarketSnapshot("binance", "BTCUSDT", now_ms, 82000, 82000, 100, 8_200_000_000, 0.0001, 1000, 82000, None, {})
    without_events = build_live_buckets([snapshot], model=1, response_range="24h", liquidation_events=[])
    with_events = build_live_buckets(
        [snapshot],
        model=1,
        response_range="24h",
        liquidation_events=[
            LiquidationEvent(
                exchange="binance",
                symbol="BTCUSDT",
                ts=now_ms,
                side="short_liquidated",
                price=82020,
                quantity=2,
                notional_usd=164_040,
            ),
            LiquidationEvent(
                exchange="binance",
                symbol="BTCUSDT",
                ts=now_ms,
                side="long_liquidated",
                price=95000,
                quantity=10,
                notional_usd=950_000,
            ),
        ],
    )

    matching = min(with_events, key=lambda bucket: abs(bucket.price_bucket - 82020))
    before_matching = min(without_events, key=lambda bucket: abs(bucket.price_bucket - matching.price_bucket))
    far = min(with_events, key=lambda bucket: abs(bucket.price_bucket - 95000))

    assert matching.consumed_score > 0
    assert matching.short_liq_usd < before_matching.short_liq_usd
    assert matching.long_liq_usd == before_matching.long_liq_usd
    assert matching.recent_liq_event_count == 1
    assert far.consumed_score == 0


def test_old_liquidation_events_do_not_consume_clusters() -> None:
    now_ms = int(time.time() * 1000)
    old_ts = now_ms - 46 * 60 * 1000
    snapshot = MarketSnapshot("binance", "BTCUSDT", now_ms, 82000, 82000, 100, 8_200_000_000, 0.0001, 1000, 82000, None, {})
    with_events = build_live_buckets(
        [snapshot],
        model=1,
        response_range="90d",
        liquidation_events=[
            LiquidationEvent(
                exchange="binance",
                symbol="BTCUSDT",
                ts=old_ts,
                side="long_liquidated",
                price=79000,
                quantity=4,
                notional_usd=316_000,
            )
        ],
    )

    assert max(bucket.consumed_score for bucket in with_events) == 0
