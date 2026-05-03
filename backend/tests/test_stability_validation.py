import asyncio
import math

from app.exchanges.base import MarketSnapshot
from app.services.collector import CollectorResult
from app.services.heatmap_service import get_heatmap
from app.services.liquidation_models import build_live_buckets, calculate_exchange_weights, exchange_weight_warnings, is_reasonable_open_interest_usd


def snapshot(exchange: str, oi_usd: float = 1_000_000, mark_price: float = 82000) -> MarketSnapshot:
    return MarketSnapshot(exchange, "BTCUSDT", 1760000000000, mark_price, mark_price, 10, oi_usd, 0.0001, 1000, mark_price, None, {})


def test_all_exchange_failure_mock_fallback(monkeypatch) -> None:
    async def fake_collect(symbol: str, **kwargs):
        return CollectorResult([], [], ["binance: down", "bybit: down"], 1760000000000, 1760000000100)

    monkeypatch.setattr("app.services.heatmap_service.collect_market_data", fake_collect)
    response = asyncio.run(get_heatmap("BTCUSDT", 1, "USD", "90d", source="live"))

    assert response.fallback is True
    assert response.source == "mock"
    assert response.warnings


def test_no_nan_or_infinity_in_live_heatmap_response(monkeypatch) -> None:
    async def fake_collect(symbol: str, **kwargs):
        return CollectorResult([snapshot("binance"), snapshot("okx", oi_usd=0)], [], [], 1760000000000, 1760000000100)

    monkeypatch.setattr("app.services.heatmap_service.collect_market_data", fake_collect)
    response = asyncio.run(get_heatmap("BTCUSDT", 3, "USD", "180d", source="live"))

    numeric_values = [response.last_price_usd]
    for bucket in response.buckets:
        numeric_values.extend([bucket.price_bucket, bucket.long_liq_usd, bucket.short_liq_usd, bucket.total_score, bucket.confidence])
    for band in response.heat_bands:
        numeric_values.extend([band.price, band.intensity])

    assert all(math.isfinite(value) for value in numeric_values)
    assert all(0 <= bucket.total_score <= 1 for bucket in response.buckets)
    assert all(0 <= bucket.confidence <= 1 for bucket in response.buckets)


def test_model2_and_model3_fallback_without_extra_data() -> None:
    buckets_1 = build_live_buckets([snapshot("binance")], model=1, response_range="90d")
    buckets_2 = build_live_buckets([snapshot("binance")], model=2, response_range="90d")
    buckets_3 = build_live_buckets([snapshot("binance")], model=3, response_range="90d", liquidation_events=[])

    assert len(buckets_1) == len(buckets_2) == len(buckets_3)
    assert all(0 <= bucket.confidence <= 1 for bucket in buckets_2 + buckets_3)


def test_currency_conversion_for_jpy(monkeypatch) -> None:
    async def fake_collect(symbol: str, **kwargs):
        return CollectorResult([snapshot("binance", mark_price=80000)], [], [], 1760000000000, 1760000000100)

    monkeypatch.setattr("app.services.heatmap_service.collect_market_data", fake_collect)
    response = asyncio.run(get_heatmap("BTCUSDT", 1, "JPY", "90d", source="live"))

    assert response.currency == "JPY"
    assert response.display_price.startswith("¥")


def test_heatmap_bucket_range_by_supported_ranges() -> None:
    for response_range in ["12h", "24h", "3d", "7d", "30d", "90d", "180d", "1y"]:
        buckets = build_live_buckets([snapshot("binance")], model=1, response_range=response_range)
        assert buckets
        assert all(bucket.price_bucket > 0 for bucket in buckets)
        assert all(0 <= bucket.total_score <= 1 for bucket in buckets)


def test_exchange_weight_fallback_renormalizes_selected_exchanges() -> None:
    weights = calculate_exchange_weights([snapshot("binance", oi_usd=0), snapshot("okx", oi_usd=0)])

    assert round(sum(weight.weight for weight in weights), 8) == 1
    assert {weight.exchange for weight in weights} == {"binance", "okx"}


def test_abnormal_open_interest_guard_excludes_extreme_values() -> None:
    normal = snapshot("binance", oi_usd=1_000_000)
    extreme = snapshot("mexc", oi_usd=900_000_000_000)

    assert is_reasonable_open_interest_usd(normal) is True
    assert is_reasonable_open_interest_usd(extreme) is False
    weights = calculate_exchange_weights([normal, extreme])
    assert len(weights) == 1
    assert weights[0].exchange == "binance"
    assert weights[0].weight == 1


def test_exchange_weight_skew_warning() -> None:
    warnings = exchange_weight_warnings(calculate_exchange_weights([snapshot("binance", oi_usd=90_000_000), snapshot("bybit", oi_usd=1_000_000)]))

    assert warnings
    assert "unusually high" in warnings[0]
