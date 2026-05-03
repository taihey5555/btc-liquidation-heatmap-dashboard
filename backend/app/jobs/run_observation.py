from __future__ import annotations

import argparse
import asyncio
import logging

from app.database import init_database
from app.services.observation import run_observation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BTCUSDT heatmap observation mode")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--duration-hours", type=float, default=24)
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Run one immediate iteration without sleeping")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    init_database()
    iterations = 1 if args.dry_run else args.iterations
    try:
        run_id = asyncio.run(
            run_observation(
                symbol=args.symbol,
                interval_seconds=args.interval,
                duration_hours=args.duration_hours,
                iterations=iterations,
            )
        )
        logging.getLogger(__name__).info("Observation run %s finished", run_id)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Observation stopped")


if __name__ == "__main__":
    main()
