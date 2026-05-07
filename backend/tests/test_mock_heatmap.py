from app.services.mock_heatmap import build_mock_heatmap


def test_mock_heatmap_generation() -> None:
    model_1 = build_mock_heatmap(model=1, currency="USD")
    model_3 = build_mock_heatmap(model=3, currency="USD")

    assert model_1.symbol == "BTCUSDT"
    assert model_1.display_price.startswith("$")
    assert model_1.heat_bands[0].intensity != model_3.heat_bands[0].intensity
    assert model_1.candles[-1].close == model_1.last_price_usd


def test_mock_heatmap_can_anchor_to_reference_price() -> None:
    response = build_mock_heatmap(reference_price=91_250)

    assert response.last_price_usd == 91_250
    assert response.current_price == 91_250
    assert response.display_price == "$91,250"
    assert abs(response.candles[-1].close - 91_250) < 0.0001
