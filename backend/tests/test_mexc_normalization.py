import asyncio

from app.exchanges.mexc import MexcAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, path, params):
        if path == "/api/v1/contract/ticker":
            return FakeResponse(
                {
                    "success": True,
                    "data": {
                        "symbol": "BTC_USDT",
                        "lastPrice": 82000,
                        "fairPrice": 82005,
                        "indexPrice": 81995,
                        "fundingRate": 0.0002,
                        "volume24": 12345,
                        "amount24": 101000000,
                        "holdVol": 1200,
                        "timestamp": 1760000000000,
                    },
                }
            )
        if path == "/api/v1/contract/detail":
            return FakeResponse({"success": True, "data": {"symbol": "BTC_USDT", "contractSize": 0.0001}})
        if path == "/api/v1/contract/funding_rate/BTC_USDT":
            return FakeResponse({"success": True, "data": {"fundingRate": 0.0002, "nextSettleTime": 1760000800000, "timestamp": 1760000000100}})
        if path == "/api/v1/contract/depth/BTC_USDT":
            return FakeResponse({"asks": [[82002, 3]], "bids": [[81999, 2]], "timestamp": 1760000000200})
        raise AssertionError(path)


def test_mexc_market_snapshot_normalization() -> None:
    snapshot = asyncio.run(MexcAdapter(client=FakeClient()).get_market_snapshot("BTCUSDT"))

    assert snapshot.exchange == "mexc"
    assert snapshot.symbol == "BTC_USDT"
    assert snapshot.mark_price == 82005
    assert snapshot.index_price == 81995
    assert snapshot.open_interest == 1200
    assert snapshot.open_interest_usd == 9840.6
    assert snapshot.funding_rate == 0.0002


def test_mexc_order_book_normalization() -> None:
    order_book = asyncio.run(MexcAdapter(client=FakeClient()).get_order_book("BTCUSDT"))

    assert order_book.bids[0].price == 81999
    assert order_book.asks[0].quantity == 3
