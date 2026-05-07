from fastapi import APIRouter, Query

from app.models.schemas import LiquidationSignalResponse
from app.services.signal_service import get_liquidation_zones_signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/liquidation-zones", response_model=LiquidationSignalResponse)
async def read_liquidation_zones_signal(
    symbol: str = Query(default="BTCUSDT"),
    model: int = Query(default=1, ge=1, le=3),
    range: str = Query(default="90d"),
    source: str = Query(default="live", pattern="^(mock|live)$"),
    exchanges: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    min_intensity: float = Query(default=0.2, ge=0, le=1),
) -> LiquidationSignalResponse:
    exchange_names = [exchange.strip().lower() for exchange in exchanges.split(",") if exchange.strip()] if exchanges else None
    return await get_liquidation_zones_signal(
        symbol=symbol,
        model=model,
        response_range=range,
        source=source,
        exchanges=exchange_names,
        limit=limit,
        min_intensity=min_intensity,
    )
