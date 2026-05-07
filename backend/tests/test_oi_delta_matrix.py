import time

from app.database import create_schema, get_connection
from app.exchanges.base import MarketSnapshot
from app.services.liquidation_models import build_live_buckets
from app.services.oi_delta_service import (
    OIDeltaBucket,
    build_oi_delta_buckets,
    get_recent_oi_delta_buckets,
    record_oi_delta_buckets,
)


def snapshot(exchange: str = "binance", ts: int = 1760000000000, price: float = 82_000, oi_usd: float = 1_000_000_000) -> MarketSnapshot:
    return MarketSnapshot(exchange, "BTCUSDT", ts, price, price, 10, oi_usd, 0.0001, 1000, price, None, {})


def test_build_oi_delta_buckets_from_price_up_oi_increase() -> None:
    previous = snapshot(ts=1760000000000, price=80_000, oi_usd=1_000_000_000)
    current = snapshot(ts=1760000060000, price=82_000, oi_usd=1_300_000_000)

    buckets = build_oi_delta_buckets(current, previous)

    assert buckets
    assert {bucket.side for bucket in buckets} == {"long"}
    assert all(bucket.price_bucket < current.mark_price for bucket in buckets)
    assert all(0 <= bucket.score <= 1 for bucket in buckets)


def test_build_oi_delta_buckets_from_price_down_oi_increase() -> None:
    previous = snapshot(ts=1760000000000, price=82_000, oi_usd=1_000_000_000)
    current = snapshot(ts=1760000060000, price=80_000, oi_usd=1_300_000_000)

    buckets = build_oi_delta_buckets(current, previous)

    assert buckets
    assert {bucket.side for bucket in buckets} == {"short"}
    assert all(bucket.price_bucket > current.mark_price for bucket in buckets)


def test_build_oi_delta_buckets_records_realistic_minute_delta() -> None:
    previous = snapshot(ts=1760000000000, price=81_000, oi_usd=8_707_654_566)
    current = snapshot(ts=1760000060000, price=81_020, oi_usd=8_709_142_613)

    buckets = build_oi_delta_buckets(current, previous)

    assert buckets
    assert sum(bucket.oi_delta_usd for bucket in buckets) > 1_000_000


def test_record_and_read_oi_delta_buckets(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "heatmap.db"

    def connection():
        return get_connection(database_path)

    with connection() as db:
        create_schema(db)
        db.execute(
            """
            INSERT INTO market_snapshots (
                exchange, symbol, ts, mark_price, index_price, open_interest,
                open_interest_usd, funding_rate, volume_24h, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("binance", "BTCUSDT", 1760000000000, 80_000, 80_000, 10, 1_000_000_000, 0.0001, 1000, "{}"),
        )
        db.commit()

    monkeypatch.setattr("app.services.oi_delta_service.get_connection", connection)
    record_oi_delta_buckets(snapshot(ts=1760000060000, price=82_000, oi_usd=1_300_000_000))

    with connection() as db:
        rows = db.execute("SELECT * FROM oi_delta_buckets").fetchall()

    assert len(rows) == 5


def test_model2_uses_persisted_oi_delta_matrix() -> None:
    now_ms = int(time.time() * 1000)
    current = snapshot(ts=now_ms, price=82_000, oi_usd=1_200_000_000)
    model1 = build_live_buckets([current], model=1, response_range="24h")
    delta_buckets = [
        OIDeltaBucket(
            exchange="binance",
            symbol="BTCUSDT",
            ts=now_ms - 30_000,
            price_bucket=80_000,
            side="long",
            oi_delta_usd=350_000_000,
            score=0.9,
            confidence=0.8,
            source_snapshot_ts=now_ms - 30_000,
            previous_snapshot_ts=now_ms - 90_000,
        )
    ]

    model2 = build_live_buckets([current], model=2, response_range="24h", oi_delta_buckets=delta_buckets)
    bucket1 = min(model1, key=lambda bucket: abs(bucket.price_bucket - 80_000))
    bucket2 = min(model2, key=lambda bucket: abs(bucket.price_bucket - 80_000))

    assert bucket2.long_liq_usd > bucket1.long_liq_usd
    assert max(bucket.confidence for bucket in model2) >= max(bucket.confidence for bucket in model1)


def test_old_oi_delta_bucket_decays_out_of_range() -> None:
    current = snapshot(price=82_000, oi_usd=1_200_000_000)
    old_delta = OIDeltaBucket(
        exchange="binance",
        symbol="BTCUSDT",
        ts=int(time.time() * 1000) - 48 * 60 * 60 * 1000,
        price_bucket=80_000,
        side="long",
        oi_delta_usd=900_000_000,
        score=1,
        confidence=1,
        source_snapshot_ts=0,
        previous_snapshot_ts=0,
    )

    model_without_delta = build_live_buckets([current], model=2, response_range="12h")
    model_with_old_delta = build_live_buckets([current], model=2, response_range="12h", oi_delta_buckets=[old_delta])

    assert [bucket.model_dump() for bucket in model_with_old_delta] == [bucket.model_dump() for bucket in model_without_delta]
