from fastapi import APIRouter

from app.exchanges import binance, bybit, gate, mexc, okx
from app.models.schemas import ExchangeStatus

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.get("/status", response_model=list[ExchangeStatus])
def read_exchange_status() -> list[ExchangeStatus]:
    return [
        ExchangeStatus(**binance.adapter.status()),
        ExchangeStatus(**bybit.adapter.status()),
        ExchangeStatus(**okx.adapter.status()),
        ExchangeStatus(**gate.adapter.status()),
        ExchangeStatus(**mexc.adapter.status()),
    ]
