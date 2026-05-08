import asyncio

from fastapi.testclient import TestClient

from app.database import create_schema, get_connection
from app.main import app
from app.models.schemas import HeatmapBucket
from app.models.schemas import TopClustersResponse, TopClusterZone
from app.services.bot_threshold_report import generate_bot_threshold_report
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


def test_bot_threshold_report_generation(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)
    now_ms = 1_760_000_000_000
    with get_connection(tmp_path / "heatmap.db") as connection:
        for index in range(12):
            connection.execute(
                """
                INSERT INTO market_snapshots (
                    exchange, symbol, ts, mark_price, index_price, open_interest,
                    open_interest_usd, funding_rate, volume_24h, raw_json
                ) VALUES (?, 'BTCUSDT', ?, 80000, 80000, 100, 500000000, 0.001, 1000, '{}')
                """,
                ("binance" if index % 2 == 0 else "bybit", now_ms + index * 60_000),
            )
        connection.execute(
            """
            INSERT INTO oi_delta_buckets (
                exchange, symbol, ts, price_bucket, side, oi_delta_usd,
                score, confidence, source_snapshot_ts, previous_snapshot_ts, raw_json
            ) VALUES ('binance', 'BTCUSDT', ?, 79000, 'long', 250000000, 0.84, 0.78, ?, ?, '{}')
            """,
            (now_ms, now_ms, now_ms - 60_000),
        )
        connection.execute(
            """
            INSERT INTO liquidation_events (
                exchange, symbol, ts, side, price, quantity, notional_usd, event_hash, raw_json
            ) VALUES ('binance', 'BTCUSDT', ?, 'long_liquidated', 79200, 2, 158400, 'x', '{}')
            """,
            (now_ms,),
        )
        connection.commit()

    async def fetcher(**_kwargs):
        return TopClustersResponse(
            symbol="BTCUSDT",
            source="live",
            fallback=False,
            current_price=80_000,
            generated_at=1_760_000_000,
            data_freshness_ms=500,
            ranges=["24h", "3d"],
            exchanges_used=["binance", "bybit"],
            warnings=[],
            top_clusters=[
                TopClusterZone(range="24h", model=3, price=79_000, side="long", distance_pct=-1.25, relative_intensity=0.8, confidence=0.77, consumed_score=0.1, total_score=0.9, estimated_liq_usd=900_000_000),
                TopClusterZone(range="3d", model=3, price=82_000, side="short", distance_pct=2.5, relative_intensity=0.7, confidence=0.72, consumed_score=0.0, total_score=0.82, estimated_liq_usd=700_000_000),
            ],
            nearest_long_liq_below=[],
            nearest_short_liq_above=[],
        )

    report = asyncio.run(generate_bot_threshold_report(cluster_fetcher=fetcher, persist=True))

    assert report["threshold_candidates"]["recommended_env"]["LIQ_HEATMAP_MODEL"] == "3"
    assert report["threshold_candidates"]["profiles"]["balanced"]["min_intensity"] >= 0.22
    assert report["threshold_candidates"]["profiles"]["balanced"]["min_estimated_liq_usd"] >= 150_000_000
    assert report["observation_report_id"] > 0
    assert "Bot Threshold Report" in report["markdown"]


def test_bot_threshold_report_api_endpoint(tmp_path, monkeypatch) -> None:
    setup_tmp_db(tmp_path, monkeypatch)

    async def fake_report(**_kwargs):
        return {"symbol": "BTCUSDT", "threshold_candidates": {"profiles": {"balanced": {"min_intensity": 0.3}}}, "markdown": "ok"}

    monkeypatch.setattr("app.routers.observation.generate_bot_threshold_report", fake_report)
    client = TestClient(app)

    response = client.get("/api/observation/reports/bot-thresholds?symbol=BTCUSDT&lookback_hours=24")

    assert response.status_code == 200
    assert response.json()["threshold_candidates"]["profiles"]["balanced"]["min_intensity"] == 0.3
