import asyncio

import pytest

from app.exchanges.binance import BinanceAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, path, params):
        if path == "/fapi/v1/premiumIndex":
            return FakeResponse(
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "82000.10",
                    "indexPrice": "81990.50",
                    "lastFundingRate": "0.0001",
                    "nextFundingTime": "1760000000000",
                }
            )
        if path == "/fapi/v1/openInterest":
            return FakeResponse({"symbol": "BTCUSDT", "openInterest": "12345.67", "time": 1760000000100})
        if path == "/fapi/v1/ticker/24hr":
            return FakeResponse({"symbol": "BTCUSDT", "lastPrice": "82002.00", "volume": "9876.5", "quoteVolume": "800000000"})
        if path == "/fapi/v1/depth":
            return FakeResponse({"E": 1760000000200, "bids": [["81999", "1.2"]], "asks": [["82001", "0.8"]]})
        raise AssertionError(path)


def test_binance_market_snapshot_normalization() -> None:
    asyncio.run(_assert_binance_market_snapshot_normalization())


async def _assert_binance_market_snapshot_normalization() -> None:
    adapter = BinanceAdapter(client=FakeClient())
    snapshot = await adapter.get_market_snapshot("BTCUSDT")
    orderbook = await adapter.get_order_book("BTCUSDT")

    assert snapshot.exchange == "binance"
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.mark_price == 82000.10
    assert snapshot.index_price == 81990.50
    assert snapshot.funding_rate == 0.0001
    assert snapshot.open_interest == 12345.67
    assert snapshot.open_interest_usd == pytest.approx(12345.67 * 82000.10)
    assert orderbook.bids[0].price == 81999
    assert orderbook.asks[0].quantity == 0.8
