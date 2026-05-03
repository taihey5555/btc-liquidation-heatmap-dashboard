import asyncio

from fastapi.testclient import TestClient

from app.database import create_schema, get_connection
from app.main import app
from app.models.schemas import HeatmapBucket
from app.services.mock_heatmap import build_mock_heatmap
from app.services.observation import (
    create_observation_run,
    detect_anomalies,
    extract_clusters,
    generate_observation_report,
    get_latest_report,
    record_observation_snapshot,
    run_observation,
)


def strong_heatmap(model: int = 1):
    response = build_mock_heatmap(model=model)
    response.source = "live"
    response.exchanges_used = ["binance", "bybit"]
    response.exchange_weights[0].open_interest_usd = 600_000_000
    response.exchange_weights[1].open_interest_usd = 400_000_000
    response.buckets = [
        HeatmapBucket(ts=1760000000, price_bucket=response.last_price_usd - 1000, long_liq_usd=150_000_000, short_liq_usd=10_000_000, total_score=0.82, confidence=0.72),
        HeatmapBucket(ts=1760000000, price_bucket=response.last_price_usd + 1000, long_liq_usd=12_000_000, short_liq_usd=180_000_000, total_score=0.91, confidence=0.76),
    ]
    return response


def setup_tmp_db(tmp_path, monkeypatch):
    database_path = tmp_path / "heatmap.db"
    with get_connection(database_path) as connection:
        create_schema(connection)
    monkeypatch.setattr("app.database.get_settings", lambda: type("Settings", (), {"database_path": database_path})())
    return database_path


def test_observation_snapshot_insert(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)
    run_id = create_observation_run("BTCUSDT", 60)
    snapshot_id = record_observation_snapshot(run_id, strong_heatmap())

    assert snapshot_id > 0
    with get_connection(tmp_path / "heatmap.db") as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM observation_snapshots").fetchone()["count"]
    assert count == 1


def test_cluster_extraction() -> None:
    clusters = extract_clusters(strong_heatmap())

    assert {cluster.direction for cluster in clusters} >= {"long_liquidation_cluster", "short_liquidation_cluster"}
    assert all(cluster.message_hash for cluster in clusters)


def test_anomaly_detection() -> None:
    response = strong_heatmap()
    response.fallback = True
    response.warnings = ["binance: timeout"]

    anomalies = detect_anomalies(1, response)

    assert {anomaly.anomaly_type for anomaly in anomalies} >= {"fallback", "response_warning", "exchange_api_failure"}


def test_report_generation(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)
    run_id = create_observation_run("BTCUSDT", 60)
    record_observation_snapshot(run_id, strong_heatmap())
    report = generate_observation_report(run_id)

    assert report.report_json["snapshot_count"] == 1
    assert "Telegram Threshold" in report.report_markdown


def test_observation_job_dry_run(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)

    async def fetcher(symbol: str, model: int):
        return strong_heatmap(model)

    run_id = asyncio.run(run_observation("BTCUSDT", interval_seconds=1, duration_hours=0.01, heatmap_fetcher=fetcher, iterations=1))

    with get_connection(tmp_path / "heatmap.db") as connection:
        snapshots = connection.execute("SELECT COUNT(*) AS count FROM observation_snapshots WHERE run_id = ?", (run_id,)).fetchone()["count"]
    assert snapshots == 3


def test_observation_api_endpoints(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)
    run_id = create_observation_run("BTCUSDT", 60)
    record_observation_snapshot(run_id, strong_heatmap())
    generate_observation_report(run_id)
    client = TestClient(app)

    assert client.get("/api/observation/runs").status_code == 200
    assert client.get(f"/api/observation/runs/{run_id}").status_code == 200
    assert client.get("/api/observation/reports/latest").status_code == 200
    assert client.get("/api/observation/anomalies?run_id=latest").status_code == 200
    assert client.get("/api/observation/clusters?run_id=latest").status_code == 200
    assert get_latest_report() is not None
