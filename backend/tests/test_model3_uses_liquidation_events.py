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
