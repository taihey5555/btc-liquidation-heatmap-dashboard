import sqlite3
from pathlib import Path

from .config import get_settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    mark_price REAL NOT NULL,
    index_price REAL NOT NULL,
    open_interest REAL NOT NULL,
    open_interest_usd REAL NOT NULL,
    funding_rate REAL NOT NULL,
    volume_24h REAL NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS liquidation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    notional_usd REAL NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS heatmap_buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    model INTEGER NOT NULL,
    range TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price_bucket REAL NOT NULL,
    long_liq_usd REAL NOT NULL,
    short_liq_usd REAL NOT NULL,
    total_score REAL NOT NULL,
    confidence REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_status (
    exchange TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    last_success_ts INTEGER,
    last_error TEXT,
    latency_ms INTEGER
);
"""


def get_connection(database_path: Path | None = None) -> sqlite3.Connection:
    path = database_path or get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()


def init_database(database_path: Path | None = None) -> None:
    with get_connection(database_path) as connection:
        create_schema(connection)
