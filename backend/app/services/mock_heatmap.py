from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.models.schemas import (
    Candle,
    ExchangeWeight,
    HeatBand,
    HeatmapBucket,
    HeatmapResponse,
    NetPoint,
    ProfileRow,
)

PRICE_MIN = 75000
PRICE_MAX = 81950
FX_USD_JPY = 157.0
X_TICKS = [
    "05-02 15:00",
    "05-02 17:20",
    "05-02 19:40",
    "05-02 22:00",
    "05-03 00:20",
    "05-03 02:40",
    "05-03 05:00",
    "05-03 07:20",
    "05-03 09:40",
    "05-03 12:00",
    "05-03 14:20",
]


def seeded_noise(index: int) -> float:
    return math.sin(index * 1.73) * 0.5 + math.sin(index * 0.41) * 0.34 + math.cos(index * 0.19) * 0.16


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def build_candles() -> list[Candle]:
    last = 78120.0
    candles: list[Candle] = []
    for index in range(245):
        drift = 2 if index < 80 else 8 if index < 150 else 2 if index < 190 else -18
        shock = 710 if index == 160 else -28 if 160 < index < 173 else 0
        change = drift + seeded_noise(index) * 48 + shock
        open_price = last
        close = clamp(open_price + change, 75150, 81650)
        high = max(open_price, close) + 22 + abs(seeded_noise(index + 8)) * 52
        low = min(open_price, close) - 18 - abs(seeded_noise(index + 17)) * 48
        last = close
        tick = X_TICKS[math.floor((index / 244) * (len(X_TICKS) - 1))]
        candles.append(Candle(time=tick, open=open_price, high=high, low=low, close=close))
    return candles


def build_heat_bands(model: int, threshold: int = 0) -> list[HeatBand]:
    anchors = [81280, 80980, 80310, 79900, 79680, 79300, 79080, 78720, 77940, 77500, 76960, 76780, 75880, 75320]
    bands: list[HeatBand] = []
    for anchor_index, price in enumerate(anchors):
        row_count = 4 if anchor_index % 3 == 0 else 3
        for row in range(row_count):
            start = int(clamp((anchor_index * 17 + row * 29 + model * 9) % 175, 0, 210))
            length = 70 + ((anchor_index * 23 + row * 13) % 130)
            intensity = clamp(0.24 + ((anchor_index + row + model) % 5) * 0.16 + model * 0.03, 0.25, 0.98)
            bands.append(
                HeatBand(
                    price=price - row * 72 + model * 18,
                    start=start,
                    end=int(clamp(start + length, 34, 244)),
                    intensity=intensity,
                )
            )

    bands.extend(
        [
            HeatBand(price=79070, start=8, end=158, intensity=1.0),
            HeatBand(price=77490, start=8, end=244, intensity=0.97),
            HeatBand(price=76670, start=8, end=244, intensity=0.58 + model * 0.03),
            HeatBand(price=81380, start=8, end=244, intensity=0.48 + model * 0.03),
        ]
    )
    return [band for band in bands if band.intensity * 100 >= threshold]


def build_profile() -> list[ProfileRow]:
    profile: list[ProfileRow] = []
    for index in range(84):
        price = PRICE_MIN + (index / 83) * (PRICE_MAX - PRICE_MIN)
        hot = math.exp(-((price - 77500) / 330) ** 2) * 0.95 + math.exp(-((price - 79000) / 520) ** 2) * 0.7
        upper = math.exp(-((price - 79900) / 390) ** 2) * 0.55
        profile.append(
            ProfileRow(
                price=price,
                long=clamp((hot + max(0, seeded_noise(index + 20)) * 0.28) * 100, 2, 112),
                short=clamp((upper + max(0, seeded_noise(index + 4)) * 0.35) * 100, 2, 98),
            )
        )
    return profile


def build_buckets(model: int, response_range: str) -> list[HeatmapBucket]:
    now = datetime.now(UTC)
    buckets: list[HeatmapBucket] = []
    for index in range(72):
        price_bucket = PRICE_MIN + (index / 71) * (PRICE_MAX - PRICE_MIN)
        long_liq = max(0.0, seeded_noise(index + model) + 0.55) * 2_800_000
        short_liq = max(0.0, seeded_noise(index + 11 + model) + 0.48) * 2_300_000
        total = long_liq + short_liq
        buckets.append(
            HeatmapBucket(
                ts=int((now - timedelta(hours=72 - index)).timestamp()),
                price_bucket=price_bucket,
                long_liq_usd=long_liq,
                short_liq_usd=short_liq,
                total_score=total / 5_100_000,
                confidence=clamp(0.62 + model * 0.07 + (0.05 if response_range == "90d" else 0), 0, 0.93),
            )
        )
    return buckets


def build_net(candles: list[Candle]) -> list[NetPoint]:
    return [
        NetPoint(time=candle.time, value=82 - seeded_noise(index + 11) * 18 - (candle.close - 78000) / 70)
        for index, candle in enumerate(candles)
    ]


def build_mock_heatmap(symbol: str = "BTCUSDT", model: int = 1, currency: str = "USD", response_range: str = "90d") -> HeatmapResponse:
    normalized_symbol = symbol.upper()
    normalized_currency = currency.upper()
    normalized_model = int(clamp(model, 1, 3))
    candles = build_candles()
    last_price = candles[-1].close
    display_price = f"${last_price:,.0f}" if normalized_currency == "USD" else f"¥{last_price * FX_USD_JPY:,.0f}"

    return HeatmapResponse(
        symbol=normalized_symbol,
        model=normalized_model,
        currency=normalized_currency,
        range=response_range,
        source="mock",
        fallback=False,
        exchanges_used=["mock"],
        generated_at=int(datetime.now(UTC).timestamp()),
        warnings=[],
        data_freshness_ms=0,
        display_price=display_price,
        last_price_usd=last_price,
        fx_usd_jpy=FX_USD_JPY,
        candles=candles,
        heat_bands=build_heat_bands(normalized_model),
        profile=build_profile(),
        net=build_net(candles),
        buckets=build_buckets(normalized_model, response_range),
        exchange_weights=[
            ExchangeWeight(exchange="binance", weight=0.34),
            ExchangeWeight(exchange="bybit", weight=0.26),
            ExchangeWeight(exchange="okx", weight=0.18),
            ExchangeWeight(exchange="gate", weight=0.12),
            ExchangeWeight(exchange="mexc", weight=0.10),
        ],
    )
