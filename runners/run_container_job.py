"""Minimal runner for scheduled container executions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from data import SUPPORTED_CITIES
from pipelines.nv_local import render_city_reports_markdown, run_pipelines_for_cities


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
