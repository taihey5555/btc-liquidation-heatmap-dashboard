from fastapi import APIRouter

from app.database import get_connection
from app.exchanges import binance, bybit, gate, mexc, okx
from app.models.schemas import ExchangeStatus

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.get("/status", response_model=list[ExchangeStatus])
def read_exchange_status() -> list[ExchangeStatus]:
    statuses = {
        "binance": ExchangeStatus(exchange="binance", enabled=True),
        "bybit": ExchangeStatus(exchange="bybit", enabled=True),
        "okx": ExchangeStatus(**okx.adapter.status()),
        "gate": ExchangeStatus(**gate.adapter.status()),
        "mexc": ExchangeStatus(**mexc.adapter.status()),
    }
    with get_connection() as connection:
        rows = connection.execute("SELECT exchange, enabled, last_success_ts, last_error, latency_ms FROM exchange_status").fetchall()
    for row in rows:
        statuses[row["exchange"]] = ExchangeStatus(
            exchange=row["exchange"],
            enabled=bool(row["enabled"]),
            last_success_ts=row["last_success_ts"],
            last_error=row["last_error"],
            latency_ms=row["latency_ms"],
        )
    return [statuses[name] for name in ("binance", "bybit", "okx", "gate", "mexc")]
