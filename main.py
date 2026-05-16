"""CLI and container entrypoint for NV Local pipeline runs."""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def run_container_mode(city: str) -> int:
    """Run all topics for a single city and save results to the database.

    Returns:
        0 on success, 1 if any topic failed, any report failed to save,
        or the SQS enqueue failed.
    """
    from pipelines.nv_local import run_pipeline
    from utils.report.storage import save_report
    from utils.sqs_client import enqueue_pipeline_failure, enqueue_report
    from utils.supabase_client import get_supported_regions_from_db

    logger = logging.getLogger(__name__)

    # Validate region before spending API credits
    try:
        supported_regions = get_supported_regions_from_db()
    except Exception as e:
        logger.error(f"Failed to get supported regions: {e}")
        return 1

    if city not in supported_regions:
        logger.error(f"Region '{city}' not in supported regions: {supported_regions}")
        return 1

    logger.info(f"Running pipeline for region={city} (all topics)")
    failures = []
    report_id: int | None = None

    # Pipeline handles all topics internally
    try:
        result = run_pipeline(city)
    except Exception as e:
        logger.error(f"Pipeline failed for {city}: {e}")
        enqueue_pipeline_failure(city, [f"{city} (pipeline invocation)"], None)
        return 1

    # Save per-topic results to Supabase
    topic_results = result.get("topic_results", {})
    for topic, topic_data in topic_results.items():
        label = f"{city} ({topic})"
        try:
            rid = save_report(city, topic, topic_data)
            if rid is None:
                logger.error(f"Failed to save report: {label}")
                failures.append(label)
            else:
                report_id = rid
                logger.info(f"Completed: {label} (report_id={report_id})")
        except Exception as e:
            logger.error(f"Failed to save report: {label} — {e}")
            failures.append(label)

    # Enqueue SQS message so the Email Lambda can send the report
    if report_id is not None:
        if not enqueue_report(city, report_id):
            failures.append(f"{city} (SQS enqueue)")

    if failures:
        logger.error(f"Pipeline failures: {failures}")
        enqueue_pipeline_failure(city, failures, report_id)
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
