from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "BTCUSDT Liquidation Heatmap API"
    database_path: Path = Path(__file__).resolve().parents[1] / "heatmap.db"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
