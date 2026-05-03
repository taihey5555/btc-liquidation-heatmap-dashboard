from __future__ import annotations

import time

import httpx

from app.exchanges.base import (
    FundingRateSnapshot,
    MarketSnapshot,
    OpenInterestSnapshot,
    OrderBookLevel,
    OrderBookSnapshot,
    TickerSnapshot,
    to_float,
    to_int,
)

BASE_URL = "https://fapi.binance.com"
TIMEOUT = httpx.Timeout(7.0, connect=4.0)


class BinanceAdapter:
    name = "binance"
    enabled = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    async def _get(self, path: str, params: dict[str, object]) -> dict:
        if self._client is not None:
            response = await self._client.get(path, params=params)
        else:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
                response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/fapi/v1/premiumIndex", {"symbol": normalized})
        now = int(time.time() * 1000)
        return FundingRateSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=now,
            funding_rate=to_float(payload.get("lastFundingRate")),
            next_funding_time=to_int(payload.get("nextFundingTime")),
            raw_json=payload,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/fapi/v1/openInterest", {"symbol": normalized})
        ts = to_int(payload.get("time"), int(time.time() * 1000)) or int(time.time() * 1000)
        open_interest = to_float(payload.get("openInterest"))
        return OpenInterestSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=ts,
            open_interest=open_interest,
            open_interest_usd=0.0,
            raw_json=payload,
        )

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/fapi/v1/ticker/24hr", {"symbol": normalized})
        now = int(time.time() * 1000)
        return TickerSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=now,
            last_price=to_float(payload.get("lastPrice")),
            volume_24h=to_float(payload.get("volume")),
            turnover_24h=to_float(payload.get("quoteVolume")),
            raw_json=payload,
        )

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/fapi/v1/depth", {"symbol": normalized, "limit": depth})
        ts = to_int(payload.get("E"), int(time.time() * 1000)) or int(time.time() * 1000)
        return OrderBookSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=ts,
            bids=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in payload.get("bids", [])],
            asks=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in payload.get("asks", [])],
            raw_json=payload,
        )

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        premium = await self._get("/fapi/v1/premiumIndex", {"symbol": normalized})
        open_interest = await self.get_open_interest(normalized)
        ticker = await self.get_ticker(normalized)
        mark_price = to_float(premium.get("markPrice"), ticker.last_price)
        index_price = to_float(premium.get("indexPrice"), mark_price)
        oi = open_interest.open_interest
        # Binance USD-M BTCUSDT openInterest is contract/base-asset quantity. For this MVP,
        # approximate USD notional as open_interest * mark_price.
        open_interest_usd = oi * mark_price
        return MarketSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            mark_price=mark_price,
            index_price=index_price,
            open_interest=oi,
            open_interest_usd=open_interest_usd,
            funding_rate=to_float(premium.get("lastFundingRate")),
            volume_24h=ticker.volume_24h,
            last_price=ticker.last_price,
            next_funding_time=to_int(premium.get("nextFundingTime")),
            raw_json={"premiumIndex": premium, "openInterest": open_interest.raw_json, "ticker": ticker.raw_json},
        )


adapter = BinanceAdapter()
