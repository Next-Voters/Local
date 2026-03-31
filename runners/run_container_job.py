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

from utils.supabase_client import get_supported_cities_from_db
from global_data.build_city_reports_dict import build_city_reports_dict
from pipelines.nv_local import run_pipeline
from pipelines.node.email_dispatcher import dispatch_emails_to_subscribers

logger = logging.getLogger(__name__)


def run_pipeline_instances(
    pipeline_runner: Callable[[str], dict[str, Any]],
    targets: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Execute one pipeline instance per target concurrently."""

    ordered_targets = tuple(targets)
    results_by_target: dict[str, dict[str, Any]] = {}

    if not ordered_targets:
        return results_by_target

    with ThreadPoolExecutor(max_workers=len(ordered_targets)) as executor:
        futures = {
            executor.submit(pipeline_runner, target): target
            for target in ordered_targets
        }

        for future in as_completed(futures):
            target = futures[future]

            try:
                results_by_target[target] = future.result()
            except Exception as exc:  # noqa: BLE001
                results_by_target[target] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "markdown_report": "",
                }

    return results_by_target


def render_pipeline_reports_markdown(
    results_by_target: Mapping[str, dict[str, Any]],
    targets: Sequence[str],
) -> str:
    """Render multi-target pipeline results as a markdown document."""

    sections: list[str] = []

    for target in targets:
        target_result = results_by_target.get(target, {})
        report = target_result.get("markdown_report", "")
        error_message = target_result.get("error")

        sections.append(f"## {target}")

        if error_message:
            sections.append(f"**Error:** `{error_message}`")
        elif report:
            sections.append(report)
        else:
            sections.append("_No markdown report was generated for this city._")

    return "\n\n".join(sections)


def run_pipelines_for_cities(
    cities: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Execute the NV Local pipeline concurrently for multiple cities."""

    return run_pipeline_instances(run_pipeline, cities)


def render_city_reports_markdown(
    results_by_city: Mapping[str, dict[str, Any]],
    cities: Sequence[str],
) -> str:
    """Render city pipeline results as a markdown document."""

    return render_pipeline_reports_markdown(results_by_city, cities)


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
        # Get supported cities from Supabase (no env var fallback)
        cities = get_supported_cities_from_db()
        logger.info(f"Running pipeline for {len(cities)} cities: {cities}")
    except Exception as e:
        logger.error(f"Failed to get supported cities: {e}")
        return 1

    # Run pipelines for all cities
    results_by_city = run_pipelines_for_cities(cities)
    report = render_city_reports_markdown(results_by_city, cities)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report or "", encoding="utf-8")

    if not quiet:
        print(report)

    # Build reports dictionary and dispatch emails
    try:
        reports_by_city = build_city_reports_dict(results_by_city)
        logger.info("Dispatching emails to subscribers...")
        dispatch_emails_to_subscribers(reports_by_city)
    except Exception as e:
        logger.error(f"Failed to dispatch emails: {e}")
        # Don't fail the entire job if email dispatch fails
        logger.info("Continuing despite email dispatch failure")

    errors = {
        city: result.get("error")
        for city, result in results_by_city.items()
        if result.get("error")
    }

    if errors:
        for city, message in errors.items():
            print(f"ERROR {city}: {message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
