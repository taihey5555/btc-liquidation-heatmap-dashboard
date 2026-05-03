import asyncio

from app.exchanges.base import MarketSnapshot
from app.services.heatmap_service import get_heatmap
from app.services.collector import CollectorResult


def test_ws_error_does_not_break_rest_heatmap(monkeypatch) -> None:
    async def fake_collect(symbol: str):
        return CollectorResult(
            snapshots=[
                MarketSnapshot("binance", symbol, 1760000000000, 82000, 82000, 100, 8_200_000, 0, 1000, 82000, None, {})
            ],
            statuses=[],
            warnings=[],
            started_at_ms=1760000000000,
            finished_at_ms=1760000000100,
        )

    def failing_recent(*args, **kwargs):
        raise RuntimeError("websocket table temporarily unavailable")

    monkeypatch.setattr("app.services.heatmap_service.collect_market_data", fake_collect)
    monkeypatch.setattr("app.services.heatmap_service.get_recent_liquidations", failing_recent)

    response = asyncio.run(get_heatmap(symbol="BTCUSDT", model=3, currency="USD", response_range="90d", source="live"))

    assert response.source == "live"
    assert response.fallback is False
