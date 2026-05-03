from __future__ import annotations

import asyncio
import logging

from app.exchanges.binance_ws import stream_binance_liquidations
from app.exchanges.bybit_ws import stream_bybit_liquidations
from app.exchanges.base import LiquidationEventSnapshot
from app.services.liquidation_streams import save_liquidation_event, update_websocket_status

LOGGER = logging.getLogger(__name__)


async def handle_liquidation_event(event: LiquidationEventSnapshot) -> None:
    inserted = save_liquidation_event(event)
    if inserted:
        LOGGER.info("Saved %s liquidation %s %s @ %s", event.exchange, event.side, event.quantity, event.price)


async def handle_websocket_status(exchange: str, connected: bool, error: str | None = None, last_message_ts: int | None = None) -> None:
    update_websocket_status(exchange=exchange, connected=connected, error=error, last_message_ts=last_message_ts)


async def run_liquidation_streams(stop_event: asyncio.Event | None = None) -> None:
    stop = stop_event or asyncio.Event()
    await asyncio.gather(
        stream_binance_liquidations(handle_liquidation_event, handle_websocket_status, stop),
        stream_bybit_liquidations(handle_liquidation_event, handle_websocket_status, stop),
    )
