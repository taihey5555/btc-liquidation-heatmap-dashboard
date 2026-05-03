from app.database import create_schema, get_connection
from app.exchanges.base import LiquidationEventSnapshot
from app.services.liquidation_streams import save_liquidation_event


def test_liquidation_event_dedupe(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "heatmap.db"
    with get_connection(database_path) as connection:
        create_schema(connection)
    monkeypatch.setattr("app.database.get_settings", lambda: type("Settings", (), {"database_path": database_path})())

    event = LiquidationEventSnapshot("binance", "BTCUSDT", 1760000000000, "long_liquidated", 82000, 0.1, 8200, {})

    assert save_liquidation_event(event) is True
    assert save_liquidation_event(event) is False
    with get_connection(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM liquidation_events").fetchone()["count"]
    assert count == 1
