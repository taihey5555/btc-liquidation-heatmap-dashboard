import asyncio

from fastapi.testclient import TestClient

from app.exchanges.base import MarketSnapshot
from app.main import app
from app.services.collector import CollectorResult
from app.services.signal_service import get_top_clusters_signal


def test_liquidation_zones_signal_mock_shape() -> None:
    client = TestClient(app)
    response = client.get("/api/signals/liquidation-zones?symbol=BTCUSDT&source=mock&range=90d&model=1")

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["current_price"] > 0
    assert "nearest_long_liq_below" in data
    assert "nearest_short_liq_above" in data
    assert "strongest_clusters" in data
    assert data["fallback"] is False


def test_liquidation_zones_signal_filters_by_intensity() -> None:
    client = TestClient(app)
    response = client.get("/api/signals/liquidation-zones?symbol=BTCUSDT&source=mock&min_intensity=0.8&limit=3")

    assert response.status_code == 200
    data = response.json()
    assert len(data["strongest_clusters"]) <= 3
    assert all(zone["relative_intensity"] >= 0.8 for zone in data["strongest_clusters"])


def test_top_clusters_signal_mock_shape() -> None:
    client = TestClient(app)
    response = client.get("/api/signals/top-clusters?symbol=BTCUSDT&source=mock&ranges=24h,3d&model=3&limit=10")

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["ranges"] == ["24h", "3d"]
    assert data["current_price"] > 0
    assert len(data["top_clusters"]) <= 10
    assert "nearest_long_liq_below" in data
    assert "nearest_short_liq_above" in data
    assert all(zone["range"] in {"24h", "3d"} for zone in data["top_clusters"])


def test_top_clusters_live_collects_once_for_multiple_ranges(monkeypatch) -> None:
    calls = 0

    async def fake_collect_market_data(symbol: str, exchange_names=None) -> CollectorResult:
        nonlocal calls
        calls += 1
        snapshot = MarketSnapshot(
            exchange="binance",
            symbol=symbol,
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
        return CollectorResult([snapshot], [], [], 1760000000000, 1760000000100)

    monkeypatch.setattr("app.services.signal_service.collect_market_data", fake_collect_market_data)

    response = asyncio.run(
        get_top_clusters_signal(
            symbol="BTCUSDT",
            model=3,
            ranges=["24h", "3d", "7d", "30d"],
            source="live",
            limit=10,
        )
    )

    assert calls == 1
    assert response.ranges == ["24h", "3d", "7d", "30d"]
    assert response.top_clusters
