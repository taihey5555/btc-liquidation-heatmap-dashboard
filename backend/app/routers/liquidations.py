from fastapi import APIRouter, Query

from app.database import init_database
from app.models.schemas import LiquidationEvent
from app.services.liquidation_streams import get_recent_liquidations

router = APIRouter(prefix="/api/liquidations", tags=["liquidations"])


@router.get("/recent", response_model=list[LiquidationEvent])
def read_recent_liquidations(
    symbol: str = Query(default="BTCUSDT"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LiquidationEvent]:
    init_database()
    return get_recent_liquidations(symbol=symbol, limit=limit)
