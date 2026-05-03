from app.exchanges.binance_ws import parse_binance_force_order


def test_binance_force_order_parse() -> None:
    event = parse_binance_force_order(
        {
            "e": "forceOrder",
            "E": 1760000000001,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "q": "0.25",
                "p": "82000",
                "ap": "82100",
                "z": "0.25",
                "T": 1760000000000,
            },
        }
    )

    assert event is not None
    assert event.exchange == "binance"
    assert event.side == "long_liquidated"
    assert event.price == 82100
    assert event.quantity == 0.25
    assert event.notional_usd == 20525
