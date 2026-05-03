from app.exchanges.base import MarketSnapshot
from app.services.liquidation_models import build_live_buckets, calculate_exchange_weights


def test_exchange_weight_calculation_excludes_missing_oi() -> None:
    weights = calculate_exchange_weights(
        [
            MarketSnapshot("binance", "BTCUSDT", 1, 82000, 82000, 1, 600_000, 0, 1, 82000, None, {}),
            MarketSnapshot("okx", "BTC-USDT-SWAP", 1, 82000, 82000, 1, 400_000, 0, 1, 82000, None, {}),
            MarketSnapshot("mexc", "BTC_USDT", 1, 82000, 82000, 1, 0, 0, 1, 82000, None, {}),
        ]
    )

    assert [weight.exchange for weight in weights] == ["binance", "okx"]
    assert weights[0].weight == 0.6
    assert weights[1].weight == 0.4


def test_heatmap_aggregation_with_five_exchanges() -> None:
    snapshots = [
        MarketSnapshot(exchange, "BTCUSDT", 1760000000000, 82000 + index * 10, 82000, 1, 1_000_000 * (index + 1), 0, 1, 82000, None, {})
        for index, exchange in enumerate(["binance", "bybit", "okx", "gate", "mexc"])
    ]

    buckets = build_live_buckets(snapshots, model=1, response_range="90d")

    assert buckets
    assert max(bucket.confidence for bucket in buckets) > 0.8
