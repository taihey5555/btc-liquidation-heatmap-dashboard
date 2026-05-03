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

BASE_URL = "https://api.bybit.com"
TIMEOUT = httpx.Timeout(7.0, connect=4.0)


class BybitAdapter:
    name = "bybit"
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
        payload = response.json()
        if payload.get("retCode") not in (None, 0):
            raise RuntimeError(f"Bybit API error {payload.get('retCode')}: {payload.get('retMsg')}")
        return payload

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/v5/market/tickers", {"category": "linear", "symbol": normalized})
        item = payload["result"]["list"][0]
        return TickerSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(payload.get("time"), int(time.time() * 1000)) or int(time.time() * 1000),
            last_price=to_float(item.get("lastPrice")),
            volume_24h=to_float(item.get("volume24h")),
            turnover_24h=to_float(item.get("turnover24h")),
            raw_json=payload,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get(
            "/v5/market/open-interest",
            {"category": "linear", "symbol": normalized, "intervalTime": "5min", "limit": 1},
        )
        item = payload["result"]["list"][0]
        oi = to_float(item.get("openInterest"))
        return OpenInterestSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(item.get("timestamp"), int(time.time() * 1000)) or int(time.time() * 1000),
            open_interest=oi,
            open_interest_usd=0.0,
            raw_json=payload,
        )

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/v5/market/tickers", {"category": "linear", "symbol": normalized})
        item = payload["result"]["list"][0]
        return FundingRateSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(payload.get("time"), int(time.time() * 1000)) or int(time.time() * 1000),
            funding_rate=to_float(item.get("fundingRate")),
            next_funding_time=to_int(item.get("nextFundingTime")),
            raw_json=payload,
        )

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/v5/market/orderbook", {"category": "linear", "symbol": normalized, "limit": depth})
        result = payload["result"]
        return OrderBookSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(result.get("ts"), to_int(payload.get("time"), int(time.time() * 1000))) or int(time.time() * 1000),
            bids=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in result.get("b", [])],
            asks=[OrderBookLevel(price=to_float(level[0]), quantity=to_float(level[1])) for level in result.get("a", [])],
            raw_json=payload,
        )

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        ticker_payload = await self._get("/v5/market/tickers", {"category": "linear", "symbol": normalized})
        item = ticker_payload["result"]["list"][0]
        open_interest = await self.get_open_interest(normalized)
        mark_price = to_float(item.get("markPrice"), to_float(item.get("lastPrice")))
        open_interest_usd = to_float(item.get("openInterestValue"))
        if open_interest_usd <= 0:
            # Bybit linear BTCUSDT openInterest is typically BTC quantity; for this MVP,
            # approximate USD notional as open_interest * mark_price when value is absent.
            open_interest_usd = open_interest.open_interest * mark_price
        return MarketSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=to_int(ticker_payload.get("time"), int(time.time() * 1000)) or int(time.time() * 1000),
            mark_price=mark_price,
            index_price=to_float(item.get("indexPrice"), mark_price),
            open_interest=open_interest.open_interest,
            open_interest_usd=open_interest_usd,
            funding_rate=to_float(item.get("fundingRate")),
            volume_24h=to_float(item.get("volume24h")),
            last_price=to_float(item.get("lastPrice"), mark_price),
            next_funding_time=to_int(item.get("nextFundingTime")),
            raw_json={"ticker": ticker_payload, "openInterest": open_interest.raw_json},
        )


adapter = BybitAdapter()
