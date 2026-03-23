"""Minimal runner for scheduled container executions."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from data import SUPPORTED_CITIES
from pipelines.nv_local import run_pipeline


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
    cities: Sequence[str] = SUPPORTED_CITIES,
) -> dict[str, dict[str, Any]]:
    """Execute the NV Local pipeline concurrently for multiple cities."""

    return run_pipeline_instances(run_pipeline, cities)


def render_city_reports_markdown(
    results_by_city: Mapping[str, dict[str, Any]],
    cities: Sequence[str] = SUPPORTED_CITIES,
) -> str:
    """Render city pipeline results as a markdown document."""

    return render_pipeline_reports_markdown(results_by_city, cities)


def _parse_cities(env_value: str | None) -> tuple[str, ...]:
    if not env_value:
        return SUPPORTED_CITIES
    cities = tuple(city.strip() for city in env_value.split(",") if city.strip())
    return cities or SUPPORTED_CITIES


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "y"}


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()

    cities = _parse_cities(os.getenv("NV_CITIES"))
    output_path = os.getenv("NV_OUTPUT_PATH")
    quiet = _env_flag("NV_QUIET")

    results_by_city = run_pipelines_for_cities(cities)
    report = render_city_reports_markdown(results_by_city, cities)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report or "", encoding="utf-8")

    if not quiet:
        print(report)

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
