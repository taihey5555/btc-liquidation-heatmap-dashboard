import asyncio

from app.services.collector import CollectorResult
from app.services.heatmap_service import get_heatmap


def test_heatmap_api_live_fallback(monkeypatch) -> None:
    async def fake_collect(symbol: str):
        return CollectorResult(
            snapshots=[],
            statuses=[],
            warnings=["binance: timeout", "bybit: timeout"],
            started_at_ms=1760000000000,
            finished_at_ms=1760000000100,
        )

    monkeypatch.setattr("app.services.heatmap_service.collect_market_data", fake_collect)
    response = asyncio.run(get_heatmap(symbol="BTCUSDT", model=1, currency="USD", response_range="90d", source="live"))

    assert response.fallback is True
    assert response.source == "mock"
    assert response.exchanges_used == []
    assert "binance: timeout" in response.warnings
