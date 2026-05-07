from __future__ import annotations

import argparse
import asyncio
import logging
import time

from app.database import init_database
from app.services.collector import collect_market_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect public market snapshots for liquidation heatmap models")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", type=int, default=60, help="Collection interval in seconds")
    parser.add_argument("--iterations", type=int, default=None, help="Stop after N iterations")
    parser.add_argument("--exchanges", default=None, help="Comma separated exchange list, e.g. binance,bybit,okx")
    parser.add_argument("--dry-run", action="store_true", help="Run one collection immediately and exit")
    return parser.parse_args()


async def run_collector(symbol: str, interval_seconds: int, iterations: int | None, exchanges: list[str] | None) -> None:
    logger = logging.getLogger(__name__)
    count = 0
    while iterations is None or count < iterations:
        started = time.monotonic()
        result = await collect_market_data(symbol=symbol, exchange_names=exchanges)
        logger.info(
            "collected symbol=%s snapshots=%s exchanges=%s warnings=%s freshness_ms=%s",
            symbol,
            len(result.snapshots),
            ",".join(result.exchanges_used) or "none",
            len(result.warnings),
            result.data_freshness_ms,
        )
        for warning in result.warnings:
            logger.warning(warning)
        count += 1
        if iterations is not None and count >= iterations:
            break
        sleep_seconds = max(0.0, interval_seconds - (time.monotonic() - started))
        await asyncio.sleep(sleep_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    init_database()
    exchanges = [name.strip().lower() for name in args.exchanges.split(",") if name.strip()] if args.exchanges else None
    iterations = 1 if args.dry_run else args.iterations
    try:
        asyncio.run(run_collector(args.symbol, args.interval, iterations, exchanges))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Market collector stopped")


if __name__ == "__main__":
    main()
