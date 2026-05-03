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

CREATE TABLE IF NOT EXISTS exchange_status (
    exchange TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    last_success_ts INTEGER,
    last_error TEXT,
    latency_ms INTEGER,
    websocket_connected INTEGER NOT NULL DEFAULT 0,
    websocket_last_message_ts INTEGER,
    websocket_last_error TEXT
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
