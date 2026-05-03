from __future__ import annotations

import asyncio
import logging

from app.database import init_database
from app.services.ws_manager import run_liquidation_streams


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_database()
    try:
        asyncio.run(run_liquidation_streams())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Liquidation stream job stopped")


if __name__ == "__main__":
    main()
