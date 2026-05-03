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
from app.exchanges.symbols import to_exchange_symbol

BASE_URL = "https://www.okx.com"
TIMEOUT = httpx.Timeout(7.0, connect=4.0)


class OkxAdapter:
    name = "okx"
    enabled = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def normalize_symbol(self, symbol: str) -> str:
        return to_exchange_symbol(self.name, symbol)

    async def _get(self, path: str, params: dict[str, object]) -> dict:
        if self._client is not None:
            response = await self._client.get(path, params=params)
        else:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
                response = await client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (None, "0", 0):
            raise RuntimeError(f"OKX API error {payload.get('code')}: {payload.get('msg')}")
        return payload

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/api/v5/market/ticker", {"instId": normalized})
        item = payload["data"][0]
        return TickerSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("ts"), int(time.time() * 1000)) or int(time.time() * 1000),
            last_price=to_float(item.get("last")),
            volume_24h=to_float(item.get("volCcy24h"), to_float(item.get("vol24h"))),
            turnover_24h=to_float(item.get("volCcy24h")),
            raw_json=payload,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": normalized})
        item = payload["data"][0]
        oi = to_float(item.get("oiCcy"), to_float(item.get("oi")))
        return OpenInterestSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("ts"), int(time.time() * 1000)) or int(time.time() * 1000),
            open_interest=oi,
            open_interest_usd=to_float(item.get("oiUsd")),
            raw_json=payload,
        )

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/api/v5/public/funding-rate", {"instId": normalized})
        item = payload["data"][0]
        return FundingRateSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("ts"), int(time.time() * 1000)) or int(time.time() * 1000),
            funding_rate=to_float(item.get("fundingRate")),
            next_funding_time=to_int(item.get("nextFundingTime")),
            raw_json=payload,
        )

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/api/v5/market/books", {"instId": normalized, "sz": depth})
        item = payload["data"][0]
        return OrderBookSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("ts"), int(time.time() * 1000)) or int(time.time() * 1000),
            bids=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in item.get("bids", [])],
            asks=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in item.get("asks", [])],
            raw_json=payload,
        )

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        ticker = await self.get_ticker(normalized)
        mark_payload = await self._get("/api/v5/public/mark-price", {"instType": "SWAP", "instId": normalized})
        mark_item = mark_payload["data"][0]
        funding = await self.get_funding_rate(normalized)
        open_interest = await self.get_open_interest(normalized)
        index_price = await self._get_index_price()
        mark_price = to_float(mark_item.get("markPx"), ticker.last_price)
        oi_usd = open_interest.open_interest_usd or (open_interest.open_interest * mark_price)
        return MarketSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(mark_item.get("ts"), ticker.ts) or ticker.ts,
            mark_price=mark_price,
            index_price=index_price or mark_price,
            open_interest=open_interest.open_interest,
            open_interest_usd=oi_usd,
            funding_rate=funding.funding_rate,
            volume_24h=ticker.volume_24h,
            last_price=ticker.last_price,
            next_funding_time=funding.next_funding_time,
            raw_json={
                "ticker": ticker.raw_json,
                "markPrice": mark_payload,
                "openInterest": open_interest.raw_json,
                "funding": funding.raw_json,
            },
        )

    async def _get_index_price(self) -> float | None:
        try:
            payload = await self._get("/api/v5/market/index-tickers", {"instId": "BTC-USDT"})
            return to_float(payload["data"][0].get("idxPx"))
        except Exception:
            return None


adapter = OkxAdapter()
