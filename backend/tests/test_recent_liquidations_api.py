from fastapi.testclient import TestClient

from app.database import create_schema, get_connection
from app.exchanges.base import LiquidationEventSnapshot
from app.main import app
from app.services.liquidation_streams import save_liquidation_event


def test_recent_liquidations_api(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "heatmap.db"
    with get_connection(database_path) as connection:
        create_schema(connection)
    monkeypatch.setattr("app.database.get_settings", lambda: type("Settings", (), {"database_path": database_path})())
    save_liquidation_event(LiquidationEventSnapshot("bybit", "BTCUSDT", 1760000000000, "short_liquidated", 83000, 0.2, 16600, {}))

    response = TestClient(app).get("/api/liquidations/recent?symbol=BTCUSDT&limit=10")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["exchange"] == "bybit"
    assert data[0]["side"] == "short_liquidated"
