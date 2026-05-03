from datetime import UTC, datetime

from fastapi import APIRouter

from app.models.schemas import LiquidationEvent

router = APIRouter(prefix="/api/liquidations", tags=["liquidations"])


@router.get("/recent", response_model=list[LiquidationEvent])
def read_recent_liquidations() -> list[LiquidationEvent]:
    now = int(datetime.now(UTC).timestamp())
    return [
        LiquidationEvent(
            exchange="mock",
            symbol="BTCUSDT",
            ts=now - 120,
            side="long",
            price=77480.0,
            quantity=1.82,
            notional_usd=141013.6,
        ),
        LiquidationEvent(
            exchange="mock",
            symbol="BTCUSDT",
            ts=now - 45,
            side="short",
            price=79080.0,
            quantity=1.25,
            notional_usd=98850.0,
        ),
    ]
