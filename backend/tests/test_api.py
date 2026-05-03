from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock"}


def test_heatmap_response_shape() -> None:
    response = client.get("/api/heatmap?symbol=BTCUSDT&model=2&currency=JPY&range=90d")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["model"] == 2
    assert data["currency"] == "JPY"
    assert data["source"] == "mock"
    assert data["display_price"].startswith("¥")
    assert len(data["candles"]) == 245
    assert len(data["heat_bands"]) > 0
    assert len(data["profile"]) == 84
    assert len(data["buckets"]) == 72


def test_exchanges_status() -> None:
    response = client.get("/api/exchanges/status")
    assert response.status_code == 200
    exchanges = {item["exchange"] for item in response.json()}
    assert exchanges == {"binance", "bybit", "okx", "gate", "mexc"}


def test_recent_liquidations() -> None:
    response = client.get("/api/liquidations/recent")
    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "BTCUSDT"
