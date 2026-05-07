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
    event_hash TEXT,
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

CREATE TABLE IF NOT EXISTS oi_delta_buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price_bucket REAL NOT NULL,
    side TEXT NOT NULL,
    oi_delta_usd REAL NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    source_snapshot_ts INTEGER NOT NULL,
    previous_snapshot_ts INTEGER,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_oi_delta_buckets_symbol_ts
ON oi_delta_buckets(symbol, ts);

CREATE INDEX IF NOT EXISTS idx_oi_delta_buckets_symbol_side_price
ON oi_delta_buckets(symbol, side, price_bucket);

CREATE TABLE IF NOT EXISTS exchange_status (
    exchange TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    last_success_ts INTEGER,
    last_error TEXT,
    latency_ms INTEGER,
    data_fields_available TEXT NOT NULL DEFAULT '[]',
    websocket_connected INTEGER NOT NULL DEFAULT 0,
    websocket_last_message_ts INTEGER,
    websocket_last_error TEXT
);

CREATE TABLE IF NOT EXISTS observation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    symbol TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS observation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    model INTEGER NOT NULL,
    current_price REAL NOT NULL,
    source TEXT NOT NULL,
    fallback INTEGER NOT NULL,
    exchanges_used TEXT NOT NULL DEFAULT '[]',
    total_open_interest_usd REAL NOT NULL,
    max_cluster_usd REAL NOT NULL,
    max_cluster_side TEXT,
    max_cluster_price_min REAL,
    max_cluster_price_max REAL,
    max_score REAL NOT NULL,
    max_confidence REAL NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES observation_runs(id)
);

CREATE TABLE IF NOT EXISTS observation_cluster_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    model INTEGER NOT NULL,
    direction TEXT NOT NULL,
    price_min REAL NOT NULL,
    price_max REAL NOT NULL,
    estimated_liq_usd REAL NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    exchanges_used TEXT NOT NULL DEFAULT '[]',
    message_hash TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES observation_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_observation_cluster_hash
ON observation_cluster_events(run_id, message_hash);

CREATE TABLE IF NOT EXISTS observation_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    severity TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    exchange TEXT,
    message TEXT NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES observation_runs(id)
);

CREATE TABLE IF NOT EXISTS observation_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    period_start INTEGER NOT NULL,
    period_end INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES observation_runs(id)
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
    _ensure_column(connection, "liquidation_events", "event_hash", "TEXT")
    _ensure_column(connection, "exchange_status", "websocket_connected", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "exchange_status", "websocket_last_message_ts", "INTEGER")
    _ensure_column(connection, "exchange_status", "websocket_last_error", "TEXT")
    _ensure_column(connection, "exchange_status", "data_fields_available", "TEXT NOT NULL DEFAULT '[]'")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_liquidation_events_hash
        ON liquidation_events(event_hash)
        WHERE event_hash IS NOT NULL
        """
    )
    connection.commit()


def init_database(database_path: Path | None = None) -> None:
    with get_connection(database_path) as connection:
        create_schema(connection)


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row["name"] for row in rows}:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
