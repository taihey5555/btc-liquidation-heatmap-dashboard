from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.database import init_database
from app.services.bot_threshold_report import generate_bot_threshold_report


async def _run(args) -> None:
    report = await generate_bot_threshold_report(
        symbol=args.symbol,
        lookback_hours=args.lookback_hours,
        source=args.source,
        model=args.model,
        ranges=[item.strip() for item in args.ranges.split(",") if item.strip()],
        persist=args.persist,
    )
    if args.markdown:
        print(report["markdown"])
    else:
        print(json.dumps(report, indent=2))
    if args.persist:
        logging.getLogger(__name__).info("Saved bot threshold report as observation_report_id=%s", report.get("observation_report_id"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a 24h bot threshold report from live heatmap and local DB history")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--source", default="live")
    parser.add_argument("--model", type=int, default=3)
    parser.add_argument("--ranges", default="24h,3d")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_database()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
