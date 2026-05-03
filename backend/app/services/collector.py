from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from app.database import get_connection
from app.config import get_settings
from app.exchanges import binance, bybit, gate, mexc, okx
from app.exchanges.base import ExchangeStatus, LiveExchangeAdapter, MarketSnapshot

COLLECTOR_TIMEOUT_SECONDS = 9.0

ADAPTERS_BY_NAME: dict[str, LiveExchangeAdapter] = {
    "binance": binance.adapter,
    "bybit": bybit.adapter,
    "okx": okx.adapter,
    "gate": gate.adapter,
    "mexc": mexc.adapter,
}


@dataclass(frozen=True)
class CollectorResult:
    snapshots: list[MarketSnapshot]
    statuses: list[ExchangeStatus]
    warnings: list[str]
    started_at_ms: int
    finished_at_ms: int

    @property
    def exchanges_used(self) -> list[str]:
        return [snapshot.exchange for snapshot in self.snapshots]

    @property
    def data_freshness_ms(self) -> int | None:
        if not self.snapshots:
            return None
        newest = max(snapshot.ts for snapshot in self.snapshots)
        return max(0, self.finished_at_ms - newest)


async def collect_market_data(
    symbol: str,
    adapters: list[LiveExchangeAdapter] | None = None,
    exchange_names: list[str] | None = None,
) -> CollectorResult:
    selected_adapters = adapters or _select_adapters(exchange_names)
    started = int(time.time() * 1000)
    tasks = [_collect_one(adapter, symbol) for adapter in selected_adapters]
    results = await asyncio.gather(*tasks)
    snapshots: list[MarketSnapshot] = []
    statuses: list[ExchangeStatus] = []
    warnings: list[str] = []

    for snapshot, status, warning in results:
        statuses.append(status)
        if snapshot is not None:
            snapshots.append(snapshot)
            _save_market_snapshot(snapshot)
        if warning:
            warnings.append(warning)
        _save_exchange_status(status)

    return CollectorResult(
        snapshots=snapshots,
        statuses=statuses,
        warnings=warnings,
        started_at_ms=started,
        finished_at_ms=int(time.time() * 1000),
    )


async def _collect_one(adapter: LiveExchangeAdapter, symbol: str) -> tuple[MarketSnapshot | None, ExchangeStatus, str | None]:
    start = time.perf_counter()
    try:
        snapshot = await asyncio.wait_for(adapter.get_market_snapshot(symbol), timeout=COLLECTOR_TIMEOUT_SECONDS)
    except Exception as exc:
        latency = int((time.perf_counter() - start) * 1000)
        error_message = _format_error(exc)
        status = ExchangeStatus(exchange=adapter.name, enabled=True, last_error=error_message, latency_ms=latency, data_fields_available=[])
        return None, status, f"{adapter.name}: {error_message}"

    latency = int((time.perf_counter() - start) * 1000)
    status = ExchangeStatus(
        exchange=adapter.name,
        enabled=True,
        last_success_ts=snapshot.ts,
        last_error=None,
        latency_ms=latency,
        data_fields_available=_snapshot_fields_available(snapshot),
    )
    return snapshot, status, None


def _select_adapters(exchange_names: list[str] | None) -> list[LiveExchangeAdapter]:
    enabled = [name.lower() for name in (exchange_names or list(get_settings().enabled_exchanges))]
    return [ADAPTERS_BY_NAME[name] for name in enabled if name in ADAPTERS_BY_NAME]


def _snapshot_fields_available(snapshot: MarketSnapshot) -> list[str]:
    fields: list[str] = []
    if snapshot.mark_price > 0:
        fields.append("mark_price")
    if snapshot.index_price > 0:
        fields.append("index_price")
    if snapshot.open_interest > 0:
        fields.append("open_interest")
    if snapshot.open_interest_usd > 0:
        fields.append("open_interest_usd")
    if snapshot.funding_rate != 0:
        fields.append("funding_rate")
    if snapshot.volume_24h > 0:
        fields.append("volume_24h")
    return fields


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _save_market_snapshot(snapshot: MarketSnapshot) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO market_snapshots (
                exchange, symbol, ts, mark_price, index_price, open_interest,
                open_interest_usd, funding_rate, volume_24h, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.exchange,
                snapshot.symbol,
                snapshot.ts,
                snapshot.mark_price,
                snapshot.index_price,
                snapshot.open_interest,
                snapshot.open_interest_usd,
                snapshot.funding_rate,
                snapshot.volume_24h,
                json.dumps(snapshot.raw_json, separators=(",", ":")),
            ),
        )
        connection.commit()


def _save_exchange_status(status: ExchangeStatus) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO exchange_status (exchange, enabled, last_success_ts, last_error, latency_ms, data_fields_available)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(exchange) DO UPDATE SET
                enabled = excluded.enabled,
                last_success_ts = COALESCE(excluded.last_success_ts, exchange_status.last_success_ts),
                last_error = excluded.last_error,
                latency_ms = excluded.latency_ms,
                data_fields_available = excluded.data_fields_available
            """,
            (
                status.exchange,
                1 if status.enabled else 0,
                status.last_success_ts,
                status.last_error,
                status.latency_ms,
                json.dumps(status.data_fields_available, separators=(",", ":")),
            ),
        )
        connection.commit()
