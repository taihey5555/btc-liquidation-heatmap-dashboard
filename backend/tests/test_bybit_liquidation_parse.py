from app.exchanges.bybit_ws import parse_bybit_all_liquidation


def test_bybit_all_liquidation_parse() -> None:
    events = parse_bybit_all_liquidation(
        {
            "topic": "allLiquidation.BTCUSDT",
            "type": "snapshot",
            "ts": 1760000000001,
            "data": [{"T": 1760000000000, "s": "BTCUSDT", "S": "Buy", "v": "0.4", "p": "82050"}],
        }
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == "bybit"
    assert event.side == "long_liquidated"
    assert event.price == 82050
    assert event.quantity == 0.4
    assert event.notional_usd == 32820
