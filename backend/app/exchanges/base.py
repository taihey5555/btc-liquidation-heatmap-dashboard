from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    exchange: str
    symbol: str
    ts: int
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    raw_json: dict


@dataclass(frozen=True)
class OpenInterestSnapshot:
    exchange: str
    symbol: str
    ts: int
    open_interest: float
    open_interest_usd: float
    raw_json: dict


@dataclass(frozen=True)
class FundingRateSnapshot:
    exchange: str
    symbol: str
    ts: int
    funding_rate: float
    next_funding_time: int | None
    raw_json: dict


@dataclass(frozen=True)
class TickerSnapshot:
    exchange: str
    symbol: str
    ts: int
    last_price: float
    volume_24h: float
    turnover_24h: float | None
    raw_json: dict


@dataclass(frozen=True)
class MarketSnapshot:
    exchange: str
    symbol: str
    ts: int
    mark_price: float
    index_price: float
    open_interest: float
    open_interest_usd: float
    funding_rate: float
    volume_24h: float
    last_price: float
    next_funding_time: int | None
    raw_json: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LiquidationEventSnapshot:
    exchange: str
    symbol: str
    ts: int
    side: str
    price: float
    quantity: float
    notional_usd: float
    raw_json: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExchangeStatus:
    exchange: str
    enabled: bool
    last_success_ts: int | None = None
    last_error: str | None = None
    latency_ms: int | None = None
    websocket_connected: bool = False
    websocket_last_message_ts: int | None = None
    websocket_last_error: str | None = None
    data_fields_available: list[str] = field(default_factory=list)


class LiveExchangeAdapter(Protocol):
    name: str
    enabled: bool

    def normalize_symbol(self, symbol: str) -> str:
        ...

    async def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        ...

    async def get_order_book(self, symbol: str, depth: int = 50) -> OrderBookSnapshot:
        ...

    async def get_open_interest(self, symbol: str) -> OpenInterestSnapshot:
        ...

    async def get_funding_rate(self, symbol: str) -> FundingRateSnapshot:
        ...

    async def get_ticker(self, symbol: str) -> TickerSnapshot:
        ...


class ExchangeAdapter:
    name: str
    enabled: bool = False

    def __init__(self, name: str) -> None:
        self.name = name

    def status(self) -> dict[str, object]:
        return {
            "exchange": self.name,
            "enabled": self.enabled,
            "last_success_ts": None,
            "last_error": "live public API integration is not implemented",
            "latency_ms": None,
            "websocket_connected": False,
            "websocket_last_message_ts": None,
            "websocket_last_error": None,
            "data_fields_available": [],
        }


class DisabledExchangeAdapter(ExchangeAdapter):
    pass


def to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def to_int(value: object, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    return int(float(value))
