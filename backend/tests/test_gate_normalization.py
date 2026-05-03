import asyncio

from app.exchanges.gate import GateAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, path, params):
        if path == "/futures/usdt/contracts/BTC_USDT":
            return FakeResponse(
                {
                    "name": "BTC_USDT",
                    "last_price": "82000",
                    "mark_price": "82010",
                    "index_price": "81990",
                    "funding_rate": "0.00012",
                    "funding_next_apply": 1760000800,
                    "position_size": 100000,
                    "quanto_multiplier": "0.0001",
                }
            )
        if path == "/futures/usdt/tickers":
            return FakeResponse([{"contract": "BTC_USDT", "last": "82001", "volume_24h_base": "1234", "volume_24h_quote": "101200000"}])
        if path == "/futures/usdt/order_book":
            return FakeResponse({"bids": [{"p": "81999", "s": 12}], "asks": [{"p": "82002", "s": 9}]})
        raise AssertionError(path)


def test_gate_market_snapshot_normalization() -> None:
    snapshot = asyncio.run(GateAdapter(client=FakeClient()).get_market_snapshot("BTCUSDT"))

    assert snapshot.exchange == "gate"
    assert snapshot.symbol == "BTC_USDT"
    assert snapshot.mark_price == 82010
    assert snapshot.index_price == 81990
    assert snapshot.open_interest == 10
    assert snapshot.open_interest_usd == 820100
    assert snapshot.funding_rate == 0.00012


def test_gate_order_book_normalization() -> None:
    order_book = asyncio.run(GateAdapter(client=FakeClient()).get_order_book("BTCUSDT"))

    assert order_book.bids[0].price == 81999
    assert order_book.asks[0].quantity == 9
