import asyncio

from app.exchanges.base import MarketSnapshot
from app.services.collector import collect_market_data


class NamedAdapter:
    enabled = True

    def __init__(self, name: str, should_fail: bool = False) -> None:
        self.name = name
        self.should_fail = should_fail

    def normalize_symbol(self, symbol: str) -> str:
        return symbol

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        if self.should_fail:
            raise RuntimeError("selected exchange failed")
        return MarketSnapshot(
            exchange=self.name,
            symbol=symbol,
            ts=1760000000000,
            mark_price=82000,
            index_price=82000,
            open_interest=10,
            open_interest_usd=820000,
            funding_rate=0.0001,
            volume_24h=100,
            last_price=82000,
            next_funding_time=None,
            raw_json={},
        )


def test_partial_exchange_failure_skips_failed_exchange(monkeypatch) -> None:
    monkeypatch.setattr("app.services.collector._save_market_snapshot", lambda snapshot: None)
    monkeypatch.setattr("app.services.collector._save_exchange_status", lambda status: None)

    result = asyncio.run(collect_market_data("BTCUSDT", adapters=[NamedAdapter("okx"), NamedAdapter("gate", should_fail=True), NamedAdapter("mexc")]))

    assert result.exchanges_used == ["okx", "mexc"]
    assert result.warnings == ["gate: selected exchange failed"]
