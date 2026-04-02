"""Minimal runner for scheduled container executions."""

from __future__ import annotations

import os
import sys
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module=r"^pydantic\.main$",
    message=r"(?s)^Pydantic serializer warnings:.*PydanticSerializationUnexpectedValue\(.*field_name=['\"]parsed['\"]",
)

from utils.supabase_client import get_supported_cities_from_db, get_supported_topics
from utils import report_cache
from pipelines.nv_local import run_pipeline
from pipelines.node.email_dispatcher import dispatch_emails_to_subscribers

logger = logging.getLogger(__name__)


def run_pipeline_instances(
    pipeline_runner: Callable[[str, str], dict[str, Any]],
    targets: Sequence[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Execute one pipeline instance per (city, topic) target concurrently."""

    ordered_targets = tuple(targets)
    results_by_target: dict[tuple[str, str], dict[str, Any]] = {}

    if not ordered_targets:
        return results_by_target

    with ThreadPoolExecutor(max_workers=len(ordered_targets)) as executor:
        futures = {
            executor.submit(pipeline_runner, city, topic): (city, topic)
            for city, topic in ordered_targets
        }

        for future in as_completed(futures):
            target = futures[future]
            city, topic = target

            try:
                result = future.result()
                results_by_target[target] = result
                report_cache.store(city, topic, result.get("markdown_report", ""))
            except Exception as exc:  # noqa: BLE001
                results_by_target[target] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "markdown_report": "",
                }

    return results_by_target


def render_pipeline_reports_markdown(
    results_by_target: Mapping[tuple[str, str], dict[str, Any]],
    targets: Sequence[tuple[str, str]],
) -> str:
    """Render multi-target pipeline results as a markdown document."""

    sections: list[str] = []

    for target in targets:
        city, topic = target
        label = f"{city} ({topic})" if topic else city
        target_result = results_by_target.get(target, {})
        report = target_result.get("markdown_report", "")
        error_message = target_result.get("error")

        sections.append(f"## {label}")

        if error_message:
            sections.append(f"**Error:** `{error_message}`")
        elif report:
            sections.append(report)
        else:
            sections.append(f"_No markdown report was generated for {label}._")

    return "\n\n".join(sections)


def run_pipelines_for_cities_and_topics(
    cities: Sequence[str],
    topics: Sequence[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Execute the NV Local pipeline concurrently for all (city, topic) pairs."""

    targets = [(city, topic) for city in cities for topic in topics]
    return run_pipeline_instances(run_pipeline, targets)


def render_city_topic_reports_markdown(
    results: Mapping[tuple[str, str], dict[str, Any]],
    targets: Sequence[tuple[str, str]],
) -> str:
    """Render (city, topic) pipeline results as a markdown document."""

    return render_pipeline_reports_markdown(results, targets)


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "y"}


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    output_path = os.getenv("NV_OUTPUT_PATH")
    quiet = _env_flag("NV_QUIET")

    try:
        cities = get_supported_cities_from_db()
        logger.info(f"Loaded {len(cities)} supported cities: {cities}")
    except Exception as e:
        logger.error(f"Failed to get supported cities: {e}")
        return 1

    try:
        topics = get_supported_topics()
        logger.info(f"Loaded {len(topics)} supported topics: {topics}")
    except Exception as e:
        logger.error(f"Failed to get supported topics: {e}")
        return 1

    # Run pipelines for all (city, topic) pairs
    targets = [(city, topic) for city in cities for topic in topics]
    results = run_pipeline_instances(run_pipeline, targets)
    report = render_pipeline_reports_markdown(results, targets)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report or "", encoding="utf-8")

    if not quiet:
        print(report)

    # Dispatch emails using cached reports
    try:
        all_reports = report_cache.get_all()
        logger.info("Dispatching emails to subscribers...")
        dispatch_emails_to_subscribers(all_reports)
    except Exception as e:
        logger.error(f"Failed to dispatch emails: {e}")
        logger.info("Continuing despite email dispatch failure")

    errors = {
        f"{city} ({topic})": result.get("error")
        for (city, topic), result in results.items()
        if result.get("error")
    }

    if errors:
        for label, message in errors.items():
            print(f"ERROR {label}: {message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
