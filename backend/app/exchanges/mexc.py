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

BASE_URL = "https://contract.mexc.com"
TIMEOUT = httpx.Timeout(7.0, connect=4.0)


class MexcAdapter:
    name = "mexc"
    enabled = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def normalize_symbol(self, symbol: str) -> str:
        return to_exchange_symbol(self.name, symbol)

    async def _get(self, path: str, params: dict[str, object] | None = None) -> dict:
        if self._client is not None:
            response = await self._client.get(path, params=params or {})
        else:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
                response = await client.get(path, params=params or {})
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError(f"MEXC API error {payload.get('code')}: {payload.get('message')}")
        return payload

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        normalized = self.normalize_symbol(symbol)
        item = await self._ticker(normalized)
        return TickerSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            last_price=to_float(item.get("lastPrice")),
            volume_24h=to_float(item.get("volume24")),
            turnover_24h=to_float(item.get("amount24")),
            raw_json=item,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        normalized = self.normalize_symbol(symbol)
        item = await self._ticker(normalized)
        fair_price = to_float(item.get("fairPrice"), to_float(item.get("lastPrice")))
        hold_vol = to_float(item.get("holdVol"))
        # MEXC holdVol is contract holdings. For this MVP, BTC_USDT is treated
        # as BTC-sized linear notional when direct contract size is unavailable.
        return OpenInterestSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            open_interest=hold_vol,
            open_interest_usd=hold_vol * fair_price,
            raw_json=item,
        )

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get(f"/api/v1/contract/funding_rate/{normalized}")
        item = payload.get("data", {})
        return FundingRateSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            funding_rate=to_float(item.get("fundingRate")),
            next_funding_time=to_int(item.get("nextSettleTime")),
            raw_json=payload,
        )

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get(f"/api/v1/contract/depth/{normalized}", {"limit": depth})
        return OrderBookSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(payload.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            bids=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in payload.get("bids", [])],
            asks=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in payload.get("asks", [])],
            raw_json=payload,
        )

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        ticker = await self._ticker(normalized)
        funding = await self.get_funding_rate(normalized)
        fair_price = to_float(ticker.get("fairPrice"), to_float(ticker.get("lastPrice")))
        index_price = to_float(ticker.get("indexPrice"), fair_price)
        hold_vol = to_float(ticker.get("holdVol"))
        return MarketSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(ticker.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            mark_price=fair_price,
            index_price=index_price,
            open_interest=hold_vol,
            open_interest_usd=hold_vol * fair_price,
            funding_rate=funding.funding_rate or to_float(ticker.get("fundingRate")),
            volume_24h=to_float(ticker.get("volume24")),
            last_price=to_float(ticker.get("lastPrice"), fair_price),
            next_funding_time=funding.next_funding_time,
            raw_json={"ticker": ticker, "funding": funding.raw_json},
        )

    async def _ticker(self, normalized_symbol: str) -> dict:
        payload = await self._get("/api/v1/contract/ticker", {"symbol": normalized_symbol})
        data = payload.get("data", {})
        if isinstance(data, list):
            for item in data:
                if item.get("symbol") == normalized_symbol:
                    return item
            raise RuntimeError(f"MEXC ticker missing {normalized_symbol}")
        return data


adapter = MexcAdapter()
