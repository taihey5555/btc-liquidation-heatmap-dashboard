from __future__ import annotations

import argparse
import logging

from app.database import init_database
from app.services.observation import generate_observation_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an observation report")
    parser.add_argument("--run-id", default="latest")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_database()
    report = generate_observation_report(args.run_id)
    logging.getLogger(__name__).info("Generated observation report %s for run %s", report.id, report.run_id)


if __name__ == "__main__":
    main()
