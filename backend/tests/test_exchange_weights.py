import pytest

from app.exchanges.base import MarketSnapshot
from app.services.liquidation_models import calculate_exchange_weights


def test_exchange_weights_use_open_interest_usd_ratio() -> None:
    weights = calculate_exchange_weights(
        [
            MarketSnapshot("binance", "BTCUSDT", 1, 82000, 82000, 100, 750_000, 0, 10, 82000, None, {}),
            MarketSnapshot("bybit", "BTCUSDT", 1, 82000, 82000, 100, 250_000, 0, 10, 82000, None, {}),
        ]
    )

    assert weights[0].exchange == "binance"
    assert weights[0].weight == pytest.approx(0.75)
    assert weights[1].weight == pytest.approx(0.25)
