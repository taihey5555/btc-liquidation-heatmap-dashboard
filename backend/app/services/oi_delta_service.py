from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass

from app.database import get_connection
from app.exchanges.base import MarketSnapshot

LEVERAGE_DISTRIBUTION = (
    (5, 0.10),
    (10, 0.20),
    (25, 0.30),
    (50, 0.25),
    (100, 0.15),
)
LIQUIDATION_BUFFER = 0.004
MIN_DELTA_USD = 25_000
MIN_DELTA_RATIO = 0.00002
MAX_DELTA_RATIO = 0.03
DEFAULT_BUCKET_SIZE = 250
MIN_REASONABLE_BTCUSDT_OI_USD = 10_000
MAX_REASONABLE_BTCUSDT_OI_USD = 50_000_000_000


@dataclass(frozen=True)
class OIDeltaBucket:
    exchange: str
    symbol: str
    ts: int
    price_bucket: float
    side: str
    oi_delta_usd: float
    score: float
    confidence: float
    source_snapshot_ts: int
    previous_snapshot_ts: int | None = None
    raw_json: dict | None = None


def record_oi_delta_buckets(snapshot: MarketSnapshot) -> list[OIDeltaBucket]:
    previous = get_previous_snapshot(snapshot)
    buckets = build_oi_delta_buckets(snapshot, previous)
    if buckets:
        save_oi_delta_buckets(buckets)
    return buckets


def get_previous_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT exchange, symbol, ts, mark_price, index_price, open_interest,
                   open_interest_usd, funding_rate, volume_24h, raw_json
            FROM market_snapshots
            WHERE exchange = ? AND symbol = ? AND ts < ?
            ORDER BY ts DESC, id DESC
            LIMIT 1
            """,
            (snapshot.exchange, snapshot.symbol.upper(), snapshot.ts),
        ).fetchone()
    if row is None:
        return None
    try:
        raw_json = json.loads(row["raw_json"])
    except Exception:
        raw_json = {}
    return MarketSnapshot(
        exchange=row["exchange"],
        symbol=row["symbol"],
        ts=row["ts"],
        mark_price=row["mark_price"],
        index_price=row["index_price"],
        open_interest=row["open_interest"],
        open_interest_usd=row["open_interest_usd"],
        funding_rate=row["funding_rate"],
        volume_24h=row["volume_24h"],
        last_price=row["mark_price"],
        next_funding_time=None,
        raw_json=raw_json,
    )


def build_oi_delta_buckets(current: MarketSnapshot, previous: MarketSnapshot | None, bucket_size: int = DEFAULT_BUCKET_SIZE) -> list[OIDeltaBucket]:
    if previous is None:
        return []
    if not (_finite_positive(current.mark_price) and _finite_positive(previous.mark_price)):
        return []
    if not (_reasonable_open_interest_usd(current) and _reasonable_open_interest_usd(previous)):
        return []

    delta_usd = current.open_interest_usd - previous.open_interest_usd
    min_delta = max(current.open_interest_usd * MIN_DELTA_RATIO, MIN_DELTA_USD)
    if delta_usd <= min_delta:
        return []

    capped_delta = min(delta_usd, current.open_interest_usd * MAX_DELTA_RATIO)
    price_change = current.mark_price - previous.mark_price
    side = "long" if price_change >= 0 else "short"
    raw = {
        "current_mark_price": current.mark_price,
        "previous_mark_price": previous.mark_price,
        "raw_delta_usd": delta_usd,
        "capped_delta_usd": capped_delta,
        "inference": "price up with OI up suggests long buildup; price down with OI up suggests short buildup",
    }

    buckets: list[OIDeltaBucket] = []
    for leverage, share in LEVERAGE_DISTRIBUTION:
        notional = capped_delta * share
        if side == "long":
            liq_price = current.mark_price * (1 - 1 / leverage + LIQUIDATION_BUFFER)
        else:
            liq_price = current.mark_price * (1 + 1 / leverage - LIQUIDATION_BUFFER)
        score = min(1.0, notional / max(capped_delta * 0.30, 1.0))
        buckets.append(
            OIDeltaBucket(
                exchange=current.exchange,
                symbol=current.symbol.upper(),
                ts=current.ts,
                price_bucket=_bucket_price(liq_price, bucket_size),
                side=side,
                oi_delta_usd=notional,
                score=score,
                confidence=0.56,
                source_snapshot_ts=current.ts,
                previous_snapshot_ts=previous.ts,
                raw_json={**raw, "leverage": leverage, "share": share},
            )
        )
    return buckets


def save_oi_delta_buckets(buckets: list[OIDeltaBucket]) -> None:
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO oi_delta_buckets (
                exchange, symbol, ts, price_bucket, side, oi_delta_usd, score,
                confidence, source_snapshot_ts, previous_snapshot_ts, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    bucket.exchange,
                    bucket.symbol.upper(),
                    bucket.ts,
                    bucket.price_bucket,
                    bucket.side,
                    bucket.oi_delta_usd,
                    bucket.score,
                    bucket.confidence,
                    bucket.source_snapshot_ts,
                    bucket.previous_snapshot_ts,
                    json.dumps(bucket.raw_json or {}, separators=(",", ":")),
                )
                for bucket in buckets
            ],
        )
        connection.commit()


def get_recent_oi_delta_buckets(symbol: str = "BTCUSDT", lookback_ms: int = 24 * 60 * 60 * 1000, limit: int = 2000) -> list[OIDeltaBucket]:
    min_ts = int(time.time() * 1000) - lookback_ms
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT exchange, symbol, ts, price_bucket, side, oi_delta_usd, score,
                   confidence, source_snapshot_ts, previous_snapshot_ts, raw_json
            FROM oi_delta_buckets
            WHERE symbol = ? AND ts >= ?
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (symbol.upper(), min_ts, limit),
        ).fetchall()

    buckets: list[OIDeltaBucket] = []
    for row in rows:
        try:
            raw_json = json.loads(row["raw_json"])
        except Exception:
            raw_json = {}
        buckets.append(
            OIDeltaBucket(
                exchange=row["exchange"],
                symbol=row["symbol"],
                ts=row["ts"],
                price_bucket=row["price_bucket"],
                side=row["side"],
                oi_delta_usd=row["oi_delta_usd"],
                score=row["score"],
                confidence=row["confidence"],
                source_snapshot_ts=row["source_snapshot_ts"],
                previous_snapshot_ts=row["previous_snapshot_ts"],
                raw_json=raw_json,
            )
        )
    return buckets


def _bucket_price(price: float, bucket_size: int) -> float:
    return round(price / bucket_size) * bucket_size


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _reasonable_open_interest_usd(snapshot: MarketSnapshot) -> bool:
    value = snapshot.open_interest_usd
    if not _finite_positive(value):
        return False
    if value < MIN_REASONABLE_BTCUSDT_OI_USD or value > MAX_REASONABLE_BTCUSDT_OI_USD:
        return False
    if _finite_positive(snapshot.mark_price) and value < snapshot.mark_price * 0.01:
        return False
    return True
