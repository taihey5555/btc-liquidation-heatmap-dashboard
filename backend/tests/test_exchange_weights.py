import pytest

from app.exchanges.base import MarketSnapshot
from app.services.liquidation_models import BINANCE_WEIGHT_CAP, calculate_exchange_weights


def snapshot(exchange: str, open_interest_usd: float) -> MarketSnapshot:
    return MarketSnapshot(exchange, "BTCUSDT", 1, 82000, 82000, 100, open_interest_usd, 0, 10, 82000, None, {})


def test_exchange_weights_use_open_interest_usd_ratio() -> None:
    weights = calculate_exchange_weights(
        [
            snapshot("bybit", 750_000),
            snapshot("okx", 250_000),
        ]
    )

    assert weights[0].exchange == "bybit"
    assert weights[0].weight == pytest.approx(0.75)
    assert weights[1].weight == pytest.approx(0.25)


def test_exchange_weights_apply_binance_bias_and_normalize_to_one() -> None:
    weights = calculate_exchange_weights(
        [
            snapshot("binance", 400_000),
            snapshot("bybit", 300_000),
            snapshot("okx", 300_000),
        ]
    )
    by_exchange = {weight.exchange: weight.weight for weight in weights}

    assert sum(by_exchange.values()) == pytest.approx(1.0)
    assert by_exchange["binance"] == pytest.approx(540_000 / 1_140_000)
    assert by_exchange["bybit"] == pytest.approx(300_000 / 1_140_000)
    assert by_exchange["okx"] == pytest.approx(300_000 / 1_140_000)


def test_exchange_weights_cap_binance_and_redistribute_excess() -> None:
    weights = calculate_exchange_weights(
        [
            snapshot("binance", 700_000),
            snapshot("bybit", 200_000),
            snapshot("okx", 100_000),
        ]
    )
    by_exchange = {weight.exchange: weight.weight for weight in weights}

    assert sum(by_exchange.values()) == pytest.approx(1.0)
    assert by_exchange["binance"] == pytest.approx(BINANCE_WEIGHT_CAP)
    assert by_exchange["bybit"] == pytest.approx(0.4 * (200_000 / 300_000))
    assert by_exchange["okx"] == pytest.approx(0.4 * (100_000 / 300_000))


def test_exchange_weights_skip_binance_when_unavailable() -> None:
    weights = calculate_exchange_weights(
        [
            snapshot("bybit", 600_000),
            snapshot("okx", 400_000),
        ]
    )
    by_exchange = {weight.exchange: weight.weight for weight in weights}

    assert "binance" not in by_exchange
    assert by_exchange["bybit"] == pytest.approx(0.6)
    assert by_exchange["okx"] == pytest.approx(0.4)


def test_exchange_weights_use_mock_weights_when_all_oi_invalid() -> None:
    weights = calculate_exchange_weights(
        [
            snapshot("binance", 0),
            snapshot("bybit", float("nan")),
        ]
    )
    by_exchange = {weight.exchange: weight.weight for weight in weights}

    assert sum(by_exchange.values()) == pytest.approx(1.0)
    assert by_exchange["binance"] == pytest.approx(0.34 / (0.34 + 0.26))
    assert by_exchange["bybit"] == pytest.approx(0.26 / (0.34 + 0.26))
