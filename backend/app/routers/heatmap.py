from fastapi import APIRouter, Query

from app.models.schemas import HeatmapResponse
from app.services.heatmap_service import get_heatmap

router = APIRouter(prefix="/api", tags=["heatmap"])


@router.get("/heatmap", response_model=HeatmapResponse)
async def read_heatmap(
    symbol: str = Query(default="BTCUSDT"),
    model: int = Query(default=1, ge=1, le=3),
    currency: str = Query(default="USD", pattern="^(USD|JPY|usd|jpy)$"),
    range: str = Query(default="90d"),
    source: str = Query(default="mock", pattern="^(mock|live)$"),
    exchanges: str | None = Query(default=None),
) -> HeatmapResponse:
    exchange_names = [exchange.strip().lower() for exchange in exchanges.split(",") if exchange.strip()] if exchanges else None
    return await get_heatmap(symbol=symbol, model=model, currency=currency, response_range=range, source=source, exchanges=exchange_names)
