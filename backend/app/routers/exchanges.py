from fastapi import APIRouter
import time

from app.database import get_connection, init_database
import json

from app.models.schemas import ExchangeStatus

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.get("/status", response_model=list[ExchangeStatus])
def read_exchange_status() -> list[ExchangeStatus]:
    init_database()
    statuses = {
        "binance": ExchangeStatus(exchange="binance", enabled=True, websocket_status_reason="liquidation stream job is not running or not connected"),
        "bybit": ExchangeStatus(exchange="bybit", enabled=True, websocket_status_reason="liquidation stream job is not running or not connected"),
        "okx": ExchangeStatus(exchange="okx", enabled=True, websocket_status_reason="liquidation websocket not implemented for this exchange"),
        "gate": ExchangeStatus(exchange="gate", enabled=True, websocket_status_reason="liquidation websocket not implemented for this exchange"),
        "mexc": ExchangeStatus(exchange="mexc", enabled=True, websocket_status_reason="liquidation websocket not implemented for this exchange"),
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
            websocket_status_reason=_websocket_status_reason(
                row["exchange"],
                bool(row["websocket_connected"]),
                row["websocket_last_message_ts"],
                row["websocket_last_error"],
            ),
            data_fields_available=json.loads(row["data_fields_available"] or "[]"),
        )
    return [statuses[name] for name in ("binance", "bybit", "okx", "gate", "mexc")]


def _websocket_status_reason(exchange: str, connected: bool, last_message_ts: int | None, last_error: str | None) -> str:
    if exchange not in {"binance", "bybit"}:
        return "liquidation websocket not implemented for this exchange"
    if last_error:
        return f"websocket error: {last_error}"
    if not connected:
        return "liquidation stream job is not running or not connected"
    if last_message_ts is None:
        return "connected flag is set, but no liquidation event has been received yet"
    age_ms = int(time.time() * 1000) - last_message_ts
    if age_ms > 10 * 60 * 1000:
        return "last liquidation event is stale; stream may be idle or stopped"
    return "receiving liquidation stream data"
