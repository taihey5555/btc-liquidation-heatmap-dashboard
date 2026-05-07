from __future__ import annotations

import json
import time

from app.database import get_connection
from app.exchanges.base import MarketSnapshot


def get_recent_market_snapshots(symbol: str = "BTCUSDT", lookback_ms: int = 6 * 60 * 60 * 1000, limit: int = 1000) -> list[MarketSnapshot]:
    min_ts = int(time.time() * 1000) - lookback_ms
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT exchange, symbol, ts, mark_price, index_price, open_interest,
                   open_interest_usd, funding_rate, volume_24h, raw_json
            FROM market_snapshots
            WHERE symbol = ? AND ts >= ?
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (symbol.upper(), min_ts, limit),
        ).fetchall()

    snapshots: list[MarketSnapshot] = []
    for row in rows:
        try:
            raw_json = json.loads(row["raw_json"])
        except Exception:
            raw_json = {}
        snapshots.append(
            MarketSnapshot(
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
        )
    return snapshots


def get_latest_market_snapshot(symbol: str = "BTCUSDT") -> MarketSnapshot | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT exchange, symbol, ts, mark_price, index_price, open_interest,
                   open_interest_usd, funding_rate, volume_24h, raw_json
            FROM market_snapshots
            WHERE symbol = ?
            ORDER BY ts DESC, id DESC
            LIMIT 1
            """,
            (symbol.upper(),),
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
