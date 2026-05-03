import asyncio

from app.exchanges.okx import OkxAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, path, params):
        if path == "/api/v5/market/ticker":
            return FakeResponse({"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "last": "82000", "volCcy24h": "1234", "ts": "1760000000000"}]})
        if path == "/api/v5/public/mark-price":
            return FakeResponse({"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "markPx": "82010", "ts": "1760000000100"}]})
        if path == "/api/v5/public/open-interest":
            return FakeResponse({"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "oiCcy": "1000", "oiUsd": "82010000", "ts": "1760000000200"}]})
        if path == "/api/v5/public/funding-rate":
            return FakeResponse({"code": "0", "data": [{"fundingRate": "0.0001", "nextFundingTime": "1760000800000", "ts": "1760000000300"}]})
        if path == "/api/v5/market/index-tickers":
            return FakeResponse({"code": "0", "data": [{"idxPx": "81990", "ts": "1760000000400"}]})
        if path == "/api/v5/market/books":
            return FakeResponse({"code": "0", "data": [{"ts": "1760000000500", "bids": [["81999", "2"]], "asks": [["82001", "3"]]}]})
        raise AssertionError(path)


def test_okx_market_snapshot_normalization() -> None:
    snapshot = asyncio.run(OkxAdapter(client=FakeClient()).get_market_snapshot("BTCUSDT"))

    assert snapshot.exchange == "okx"
    assert snapshot.symbol == "BTC-USDT-SWAP"
    assert snapshot.mark_price == 82010
    assert snapshot.index_price == 81990
    assert snapshot.open_interest == 1000
    assert snapshot.open_interest_usd == 82010000
    assert snapshot.funding_rate == 0.0001


def test_okx_order_book_normalization() -> None:
    order_book = asyncio.run(OkxAdapter(client=FakeClient()).get_order_book("BTCUSDT"))

    assert order_book.bids[0].price == 81999
    assert order_book.asks[0].quantity == 3
