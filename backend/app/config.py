from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


def _split_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


def _path_from_env(value: str | None, default: Path) -> Path:
    if not value:
        return default
    return Path(value).expanduser()


class Settings(BaseModel):
    app_name: str = "BTCUSDT Liquidation Heatmap API"
    database_path: Path = Path(__file__).resolve().parents[1] / "heatmap.db"
    enabled_exchanges: tuple[str, ...] = ("binance", "bybit", "okx", "gate", "mexc")
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    observation_interval_seconds: int = 60
    observation_duration_hours: int = 24
    telegram_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    default_settings = Settings()
    return Settings(
        app_name=os.getenv("BTC_HEATMAP_APP_NAME", default_settings.app_name),
        database_path=_path_from_env(
            os.getenv("BTC_HEATMAP_DATABASE_PATH"),
            default_settings.database_path,
        ),
        enabled_exchanges=_split_csv(
            os.getenv("BTC_HEATMAP_ENABLED_EXCHANGES"),
            default_settings.enabled_exchanges,
        ),
        cors_origins=_split_csv(
            os.getenv("BTC_HEATMAP_CORS_ORIGINS"),
            default_settings.cors_origins,
        ),
        observation_interval_seconds=int(
            os.getenv(
                "BTC_HEATMAP_OBSERVATION_INTERVAL_SECONDS",
                str(default_settings.observation_interval_seconds),
            )
        ),
        observation_duration_hours=int(
            os.getenv(
                "BTC_HEATMAP_OBSERVATION_DURATION_HOURS",
                str(default_settings.observation_duration_hours),
            )
        ),
        telegram_enabled=os.getenv("BTC_HEATMAP_TELEGRAM_ENABLED", "false").lower()
        == "true",
    )
