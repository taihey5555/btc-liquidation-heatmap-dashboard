from __future__ import annotations

import hashlib
import json

from app.database import get_connection
from app.exchanges.base import LiquidationEventSnapshot
from app.models.schemas import LiquidationEvent


def liquidation_event_hash(event: LiquidationEventSnapshot) -> str:
    payload = f"{event.exchange}|{event.symbol}|{event.ts}|{event.side}|{event.price:.8f}|{event.quantity:.8f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_liquidation_event(event: LiquidationEventSnapshot) -> bool:
    event_hash = liquidation_event_hash(event)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO liquidation_events (
                exchange, symbol, ts, side, price, quantity, notional_usd, event_hash, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.exchange,
                event.symbol,
                event.ts,
                event.side,
                event.price,
                event.quantity,
                event.notional_usd,
                event_hash,
                json.dumps(event.raw_json, separators=(",", ":")),
            ),
        )
        connection.commit()
        return cursor.rowcount > 0


def get_recent_liquidations(symbol: str = "BTCUSDT", limit: int = 100) -> list[LiquidationEvent]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT exchange, symbol, ts, side, price, quantity, notional_usd, raw_json
            FROM liquidation_events
            WHERE symbol = ?
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (symbol.upper(), limit),
        ).fetchall()
    events: list[LiquidationEvent] = []
    for row in rows:
        try:
            raw_json = json.loads(row["raw_json"])
        except Exception:
            raw_json = {}
        events.append(
            LiquidationEvent(
                exchange=row["exchange"],
                symbol=row["symbol"],
                ts=row["ts"],
                side=row["side"],
                price=row["price"],
                quantity=row["quantity"],
                notional_usd=row["notional_usd"],
                raw_json=raw_json,
            )
        )
    return events


def update_websocket_status(exchange: str, connected: bool, error: str | None = None, last_message_ts: int | None = None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO exchange_status (
                exchange, enabled, websocket_connected, websocket_last_message_ts, websocket_last_error
            ) VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(exchange) DO UPDATE SET
                websocket_connected = excluded.websocket_connected,
                websocket_last_message_ts = COALESCE(excluded.websocket_last_message_ts, exchange_status.websocket_last_message_ts),
                websocket_last_error = excluded.websocket_last_error
            """,
            (exchange, 1 if connected else 0, last_message_ts, error),
        )
        connection.commit()
