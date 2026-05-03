SUPPORTED_SYMBOLS = ("BTCUSDT",)
SUPPORTED_EXCHANGES = ("binance", "bybit", "okx", "gate", "mexc")

EXCHANGE_SYMBOLS = {
    "binance": {"BTCUSDT": "BTCUSDT"},
    "bybit": {"BTCUSDT": "BTCUSDT"},
    "okx": {"BTCUSDT": "BTC-USDT-SWAP"},
    "gate": {"BTCUSDT": "BTC_USDT"},
    "mexc": {"BTCUSDT": "BTC_USDT"},
}


def to_exchange_symbol(exchange: str, symbol: str) -> str:
    normalized_exchange = exchange.lower()
    upper_symbol = symbol.upper()
    mapping = EXCHANGE_SYMBOLS.get(normalized_exchange, {})
    if upper_symbol in mapping.values():
        return upper_symbol
    normalized_symbol = upper_symbol.replace("/", "").replace("-", "").replace("_", "")
    return mapping.get(normalized_symbol, normalized_symbol)


def to_internal_symbol(exchange: str, symbol: str) -> str:
    normalized_exchange = exchange.lower()
    mapping = EXCHANGE_SYMBOLS.get(normalized_exchange, {})
    reverse = {value: key for key, value in mapping.items()}
    return reverse.get(symbol.upper(), symbol.upper().replace("-", "").replace("_", ""))
