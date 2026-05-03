from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from app.database import get_connection
from app.exchanges import binance, bybit
from app.exchanges.base import ExchangeStatus, LiveExchangeAdapter, MarketSnapshot


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


async def collect_market_data(symbol: str, adapters: list[LiveExchangeAdapter] | None = None) -> CollectorResult:
    selected_adapters = adapters or [binance.adapter, bybit.adapter]
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
        snapshot = await adapter.get_market_snapshot(symbol)
    except Exception as exc:
        latency = int((time.perf_counter() - start) * 1000)
        status = ExchangeStatus(exchange=adapter.name, enabled=True, last_error=str(exc), latency_ms=latency)
        return None, status, f"{adapter.name}: {exc}"

    latency = int((time.perf_counter() - start) * 1000)
    status = ExchangeStatus(exchange=adapter.name, enabled=True, last_success_ts=snapshot.ts, last_error=None, latency_ms=latency)
    return snapshot, status, None


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
            INSERT INTO exchange_status (exchange, enabled, last_success_ts, last_error, latency_ms)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(exchange) DO UPDATE SET
                enabled = excluded.enabled,
                last_success_ts = COALESCE(excluded.last_success_ts, exchange_status.last_success_ts),
                last_error = excluded.last_error,
                latency_ms = excluded.latency_ms
            """,
            (
                status.exchange,
                1 if status.enabled else 0,
                status.last_success_ts,
                status.last_error,
                status.latency_ms,
            ),
        )
        connection.commit()
