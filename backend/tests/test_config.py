from pathlib import Path

from app.config import get_settings


def test_settings_read_vps_environment(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("BTC_HEATMAP_DATABASE_PATH", "/var/lib/btc-heatmap/heatmap.db")
    monkeypatch.setenv("BTC_HEATMAP_CORS_ORIGINS", "https://example.com,http://127.0.0.1:3000")
    monkeypatch.setenv("BTC_HEATMAP_ENABLED_EXCHANGES", "binance,bybit,okx")
    monkeypatch.setenv("BTC_HEATMAP_OBSERVATION_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("BTC_HEATMAP_OBSERVATION_DURATION_HOURS", "72")
    monkeypatch.setenv("BTC_HEATMAP_TELEGRAM_ENABLED", "false")

    settings = get_settings()

    assert settings.database_path == Path("/var/lib/btc-heatmap/heatmap.db")
    assert settings.cors_origins == ("https://example.com", "http://127.0.0.1:3000")
    assert settings.enabled_exchanges == ("binance", "bybit", "okx")
    assert settings.observation_interval_seconds == 120
    assert settings.observation_duration_hours == 72
    assert settings.telegram_enabled is False
    get_settings.cache_clear()
