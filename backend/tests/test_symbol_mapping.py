from app.exchanges.symbols import to_exchange_symbol, to_internal_symbol


def test_symbol_mapping() -> None:
    assert to_exchange_symbol("binance", "BTCUSDT") == "BTCUSDT"
    assert to_exchange_symbol("bybit", "BTCUSDT") == "BTCUSDT"
    assert to_exchange_symbol("okx", "BTCUSDT") == "BTC-USDT-SWAP"
    assert to_exchange_symbol("gate", "BTCUSDT") == "BTC_USDT"
    assert to_exchange_symbol("mexc", "BTCUSDT") == "BTC_USDT"
    assert to_internal_symbol("okx", "BTC-USDT-SWAP") == "BTCUSDT"
    assert to_internal_symbol("gate", "BTC_USDT") == "BTCUSDT"
