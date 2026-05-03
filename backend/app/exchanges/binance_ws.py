from __future__ import annotations

import asyncio
import json
import logging

import websockets

from app.exchanges.base import LiquidationEventSnapshot, to_float, to_int

LOGGER = logging.getLogger(__name__)
BINANCE_WS_URL = "wss://fstream.binance.com/ws/btcusdt@forceOrder"


def parse_binance_force_order(payload: dict) -> LiquidationEventSnapshot | None:
    order = payload.get("o")
    if not isinstance(order, dict):
        return None

    symbol = str(order.get("s", "BTCUSDT")).upper()
    raw_side = str(order.get("S", "")).upper()
    # Binance forceOrder side is the liquidation order side. A SELL forced order
    # closes a liquidated long; a BUY forced order closes a liquidated short.
    side = "long_liquidated" if raw_side == "SELL" else "short_liquidated" if raw_side == "BUY" else "unknown"
    price = to_float(order.get("ap"), to_float(order.get("p")))
    quantity = to_float(order.get("z"), to_float(order.get("q")))
    if price <= 0 or quantity <= 0:
        return None

    return LiquidationEventSnapshot(
        exchange="binance",
        symbol=symbol,
        ts=to_int(order.get("T"), to_int(payload.get("E"), 0)) or 0,
        side=side,
        price=price,
        quantity=quantity,
        notional_usd=price * quantity,
        raw_json=payload,
    )


async def stream_binance_liquidations(on_event, on_status, stop_event: asyncio.Event | None = None) -> None:
    backoff = 1.0
    while stop_event is None or not stop_event.is_set():
        try:
            await on_status("binance", True, None)
            async with websockets.connect(BINANCE_WS_URL, ping_interval=20, ping_timeout=20) as websocket:
                backoff = 1.0
                async for message in websocket:
                    try:
                        event = parse_binance_force_order(json.loads(message))
                        if event is not None:
                            await on_event(event)
                            await on_status("binance", True, None, event.ts)
                    except Exception as exc:
                        LOGGER.exception("Failed to parse Binance forceOrder message")
                        await on_status("binance", True, str(exc))
                    if stop_event is not None and stop_event.is_set():
                        break
        except Exception as exc:
            LOGGER.warning("Binance liquidation WebSocket disconnected: %s", exc)
            await on_status("binance", False, str(exc))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.8, 30.0)
