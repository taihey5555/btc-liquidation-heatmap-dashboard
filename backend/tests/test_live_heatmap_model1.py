from app.exchanges.base import MarketSnapshot
from app.services.liquidation_models import build_live_buckets


def test_live_heatmap_model1_generates_buckets() -> None:
    buckets = build_live_buckets(
        snapshots=[
            MarketSnapshot(
                exchange="binance",
                symbol="BTCUSDT",
                ts=1760000000000,
                mark_price=82000,
                index_price=82000,
                open_interest=100,
                open_interest_usd=8_200_000,
                funding_rate=0.0001,
                volume_24h=1000,
                last_price=82000,
                next_funding_time=None,
                raw_json={},
            )
        ],
        model=1,
        response_range="90d",
    )

    assert buckets
    assert all(bucket.long_liq_usd >= 0 for bucket in buckets)
    assert all(bucket.short_liq_usd >= 0 for bucket in buckets)
    assert max(bucket.total_score for bucket in buckets) == 1
