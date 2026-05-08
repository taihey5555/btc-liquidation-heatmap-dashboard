from fastapi.testclient import TestClient

from app.main import app


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
