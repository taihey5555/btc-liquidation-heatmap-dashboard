import asyncio

from app.exchanges.bybit import BybitAdapter


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, path, params):
        if path == "/v5/market/tickers":
            return FakeResponse(
                {
                    "retCode": 0,
                    "result": {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "lastPrice": "82010.5",
                                "indexPrice": "82000.1",
                                "markPrice": "82005.2",
                                "openInterest": "2222.2",
                                "openInterestValue": "182250000",
                                "turnover24h": "1200000000",
                                "volume24h": "14500",
                                "fundingRate": "-0.00002",
                                "nextFundingTime": "1760000100000",
                            }
                        ]
                    },
                    "time": 1760000000000,
                }
            )
        if path == "/v5/market/open-interest":
            return FakeResponse(
                {
                    "retCode": 0,
                    "result": {"list": [{"openInterest": "2222.2", "timestamp": "1760000000000"}]},
                    "time": 1760000000000,
                }
            )
        if path == "/v5/market/orderbook":
            return FakeResponse(
                {
                    "retCode": 0,
                    "result": {"ts": 1760000000000, "b": [["82000", "1.1"]], "a": [["82002", "0.9"]]},
                    "time": 1760000000000,
                }
            )
        raise AssertionError(path)


def test_bybit_market_snapshot_normalization() -> None:
    asyncio.run(_assert_bybit_market_snapshot_normalization())


async def _assert_bybit_market_snapshot_normalization() -> None:
    adapter = BybitAdapter(client=FakeClient())
    snapshot = await adapter.get_market_snapshot("BTCUSDT")
    orderbook = await adapter.get_order_book("BTCUSDT")

    assert snapshot.exchange == "bybit"
    assert snapshot.mark_price == 82005.2
    assert snapshot.index_price == 82000.1
    assert snapshot.open_interest == 2222.2
    assert snapshot.open_interest_usd == 182250000
    assert snapshot.funding_rate == -0.00002
    assert orderbook.bids[0].quantity == 1.1
