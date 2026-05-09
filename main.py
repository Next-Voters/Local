"""CLI and container entrypoint for NV Local pipeline runs."""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def run_container_mode(city: str) -> int:
    """Run all topics for a single city and save results to the database.

    Returns:
        0 on success, 1 if any topic failed or any report failed to save.
    """
    from pipelines.nv_local import run_pipeline
    from utils.report.storage import save_report
    from utils.supabase_client import get_supported_cities_from_db, get_supported_topics

    logger = logging.getLogger(__name__)

    # Validate city before spending API credits
    try:
        supported_cities = get_supported_cities_from_db()
    except Exception as e:
        logger.error(f"Failed to get supported cities: {e}")
        return 1

    if city not in supported_cities:
        logger.error(f"City '{city}' not in supported cities: {supported_cities}")
        return 1

    try:
        topics = get_supported_topics()
    except Exception as e:
        logger.error(f"Failed to get supported topics: {e}")
        return 1

    logger.info(f"Running pipeline for city={city}, topics={topics}")
    failures = []

    for topic in topics:
        label = f"{city} ({topic})"
        try:
            logger.info(f"Starting pipeline: {label}")
            result = run_pipeline(city, topic)
            report_id = save_report(city, topic, result)
            if report_id is None:
                logger.error(f"Failed to save report: {label}")
                failures.append(label)
            else:
                logger.info(f"Completed: {label} (report_id={report_id})")
        except Exception as e:
            logger.error(f"Failed: {label} — {e}")
            failures.append(label)

    if failures:
        logger.error(f"Pipeline failures: {failures}")
        return 1

    return 0


def run_cli_mode() -> None:
    """Interactive CLI mode with argparse."""
    from pipelines.nv_local import main as pipeline_main

    pipeline_main()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    nv_city = os.getenv("NV_CITY")

    if nv_city:
        sys.exit(run_container_mode(nv_city))
    else:
        run_cli_mode()
