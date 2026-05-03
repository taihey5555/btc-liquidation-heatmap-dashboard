from fastapi import APIRouter

from app.database import get_connection, init_database
import json

from app.models.schemas import ExchangeStatus

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.get("/status", response_model=list[ExchangeStatus])
def read_exchange_status() -> list[ExchangeStatus]:
    init_database()
    statuses = {
        "binance": ExchangeStatus(exchange="binance", enabled=True),
        "bybit": ExchangeStatus(exchange="bybit", enabled=True),
        "okx": ExchangeStatus(exchange="okx", enabled=True),
        "gate": ExchangeStatus(exchange="gate", enabled=True),
        "mexc": ExchangeStatus(exchange="mexc", enabled=True),
    }
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT exchange, enabled, last_success_ts, last_error, latency_ms, data_fields_available,
                   websocket_connected, websocket_last_message_ts, websocket_last_error
            FROM exchange_status
            """
        ).fetchall()
    for row in rows:
        statuses[row["exchange"]] = ExchangeStatus(
            exchange=row["exchange"],
            enabled=bool(row["enabled"]),
            last_success_ts=row["last_success_ts"],
            last_error=row["last_error"],
            latency_ms=row["latency_ms"],
            websocket_connected=bool(row["websocket_connected"]),
            websocket_last_message_ts=row["websocket_last_message_ts"],
            websocket_last_error=row["websocket_last_error"],
            data_fields_available=json.loads(row["data_fields_available"] or "[]"),
        )
    return [statuses[name] for name in ("binance", "bybit", "okx", "gate", "mexc")]
