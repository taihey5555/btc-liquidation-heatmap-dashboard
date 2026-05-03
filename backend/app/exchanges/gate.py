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

BASE_URL = "https://api.gateio.ws/api/v4"
TIMEOUT = httpx.Timeout(7.0, connect=4.0)


class GateAdapter:
    name = "gate"
    enabled = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def normalize_symbol(self, symbol: str) -> str:
        return to_exchange_symbol(self.name, symbol)

    async def _get(self, path: str, params: dict[str, object] | None = None):
        if self._client is not None:
            response = await self._client.get(path, params=params or {})
        else:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"Accept": "application/json"}) as client:
                response = await client.get(path, params=params or {})
        response.raise_for_status()
        return response.json()

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/futures/usdt/tickers", {"contract": normalized})
        item = payload[0] if isinstance(payload, list) else payload
        return TickerSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            last_price=to_float(item.get("last")),
            volume_24h=to_float(item.get("volume_24h_base"), to_float(item.get("volume_24h"))),
            turnover_24h=to_float(item.get("volume_24h_quote"), to_float(item.get("volume_24h_usd"))),
            raw_json=item,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        normalized = self.normalize_symbol(symbol)
        contract = await self._contract(normalized)
        mark_price = to_float(contract.get("mark_price"), to_float(contract.get("last_price")))
        position_size = to_float(contract.get("position_size"))
        multiplier = to_float(contract.get("quanto_multiplier"), 1.0)
        # Gate USDT futures position_size is contract count. For BTC_USDT direct
        # contracts, quanto_multiplier converts contracts to BTC notional.
        oi_base = position_size * multiplier
        return OpenInterestSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            open_interest=oi_base,
            open_interest_usd=oi_base * mark_price,
            raw_json=contract,
        )

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        normalized = self.normalize_symbol(symbol)
        contract = await self._contract(normalized)
        return FundingRateSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            funding_rate=to_float(contract.get("funding_rate"), to_float(contract.get("funding_rate_indicative"))),
            next_funding_time=(to_int(contract.get("funding_next_apply")) or 0) * 1000,
            raw_json=contract,
        )

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        normalized = self.normalize_symbol(symbol)
        payload = await self._get("/futures/usdt/order_book", {"contract": normalized, "limit": depth})
        return OrderBookSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            bids=[OrderBookLevel(price=to_float(level.get("p")), quantity=to_float(level.get("s"))) for level in payload.get("bids", [])],
            asks=[OrderBookLevel(price=to_float(level.get("p")), quantity=to_float(level.get("s"))) for level in payload.get("asks", [])],
            raw_json=payload,
        )

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = self.normalize_symbol(symbol)
        contract = await self._contract(normalized)
        ticker = await self.get_ticker(normalized)
        open_interest = await self.get_open_interest(normalized)
        return MarketSnapshot(
            exchange=self.name,
            symbol=normalized,
            ts=int(time.time() * 1000),
            mark_price=to_float(contract.get("mark_price"), ticker.last_price),
            index_price=to_float(contract.get("index_price"), to_float(contract.get("mark_price"), ticker.last_price)),
            open_interest=open_interest.open_interest,
            open_interest_usd=open_interest.open_interest_usd,
            funding_rate=to_float(contract.get("funding_rate"), to_float(contract.get("funding_rate_indicative"))),
            volume_24h=ticker.volume_24h,
            last_price=ticker.last_price,
            next_funding_time=(to_int(contract.get("funding_next_apply")) or 0) * 1000,
            raw_json={"contract": contract, "ticker": ticker.raw_json},
        )

    async def _contract(self, normalized_symbol: str) -> dict:
        return await self._get(f"/futures/usdt/contracts/{normalized_symbol}")


adapter = GateAdapter()
