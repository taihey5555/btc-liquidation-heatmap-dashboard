from app.database import create_schema, get_connection


def test_sqlite_schema_creation(tmp_path) -> None:
    database_path = tmp_path / "heatmap.db"
    with get_connection(database_path) as connection:
        create_schema(connection)
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    tables = {row["name"] for row in rows}
    assert "market_snapshots" in tables
    assert "liquidation_events" in tables
    assert "heatmap_buckets" in tables
    assert "exchange_status" in tables
