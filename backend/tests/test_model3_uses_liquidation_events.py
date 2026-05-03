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
