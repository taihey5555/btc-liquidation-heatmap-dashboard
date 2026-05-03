from app.models.schemas import HeatmapResponse
from app.services.mock_heatmap import build_mock_heatmap


def get_heatmap(symbol: str, model: int, currency: str, response_range: str) -> HeatmapResponse:
    return build_mock_heatmap(symbol=symbol, model=model, currency=currency, response_range=response_range)
