from __future__ import annotations

import asyncio
import json
import logging

import websockets

from app.exchanges.base import LiquidationEventSnapshot, to_float, to_int

LOGGER = logging.getLogger(__name__)
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
BYBIT_TOPIC = "allLiquidation.BTCUSDT"


def parse_bybit_all_liquidation(payload: dict) -> list[LiquidationEventSnapshot]:
    data = payload.get("data", [])
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    events: list[LiquidationEventSnapshot] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_side = str(item.get("S", ""))
        # Bybit allLiquidation docs specify Buy means a long position was
        # liquidated; Sell means a short position was liquidated.
        side = "long_liquidated" if raw_side == "Buy" else "short_liquidated" if raw_side == "Sell" else "unknown"
        price = to_float(item.get("p"))
        quantity = to_float(item.get("v"))
        if price <= 0 or quantity <= 0:
            continue
        events.append(
            LiquidationEventSnapshot(
                exchange="bybit",
                symbol=str(item.get("s", "BTCUSDT")).upper(),
                ts=to_int(item.get("T"), to_int(payload.get("ts"), 0)) or 0,
                side=side,
                price=price,
                quantity=quantity,
                notional_usd=price * quantity,
                raw_json=payload,
            )
        )
    return events


async def stream_bybit_liquidations(on_event, on_status, stop_event: asyncio.Event | None = None) -> None:
    backoff = 1.0
    subscribe_message = json.dumps({"op": "subscribe", "args": [BYBIT_TOPIC]})
    while stop_event is None or not stop_event.is_set():
        try:
            await on_status("bybit", True, None)
            async with websockets.connect(BYBIT_WS_URL, ping_interval=20, ping_timeout=20) as websocket:
                await websocket.send(subscribe_message)
                backoff = 1.0
                async for message in websocket:
                    try:
                        payload = json.loads(message)
                        if payload.get("op") == "ping":
                            await websocket.send(json.dumps({"op": "pong"}))
                            continue
                        for event in parse_bybit_all_liquidation(payload):
                            await on_event(event)
                            await on_status("bybit", True, None, event.ts)
                    except Exception as exc:
                        LOGGER.exception("Failed to parse Bybit allLiquidation message")
                        await on_status("bybit", True, str(exc))
                    if stop_event is not None and stop_event.is_set():
                        break
        except Exception as exc:
            LOGGER.warning("Bybit liquidation WebSocket disconnected: %s", exc)
            await on_status("bybit", False, str(exc))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.8, 30.0)
