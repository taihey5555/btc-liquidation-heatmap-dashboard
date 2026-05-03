import asyncio

from app.exchanges.base import MarketSnapshot
from app.services.collector import collect_market_data


class SuccessAdapter:
    name = "success"
    enabled = True

    def normalize_symbol(self, symbol: str) -> str:
        return symbol

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            exchange=self.name,
            symbol=symbol,
            ts=1760000000000,
            mark_price=82000,
            index_price=82000,
            open_interest=100,
            open_interest_usd=8_200_000,
            funding_rate=0.0001,
            volume_24h=1000,
            last_price=82000,
            next_funding_time=None,
            raw_json={},
        )


class FailingAdapter:
    name = "failing"
    enabled = True

    def normalize_symbol(self, symbol: str) -> str:
        return symbol

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        raise RuntimeError("upstream unavailable")


def test_collector_partial_failure_continues(monkeypatch) -> None:
    monkeypatch.setattr("app.services.collector._save_market_snapshot", lambda snapshot: None)
    monkeypatch.setattr("app.services.collector._save_exchange_status", lambda status: None)
    result = asyncio.run(collect_market_data("BTCUSDT", adapters=[SuccessAdapter(), FailingAdapter()]))

    assert result.exchanges_used == ["success"]
    assert len(result.warnings) == 1
    assert "upstream unavailable" in result.warnings[0]
