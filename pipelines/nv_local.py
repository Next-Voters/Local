"""NV Local pipeline entry points."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.email_sender import send_email_to_subscribers
from pipelines.node.legislation_finder import legislation_finder_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.politician_commentary import politician_commentary_chain
from pipelines.node.report_formatter import report_formatter_chain
from data import SUPPORTED_CITIES
from pipelines.node.summary_writer import summary_writer_chain

chain = (
    legislation_finder_chain
    | content_retrieval_chain
    | note_taker_chain
    | summary_writer_chain
    | politician_commentary_chain
    | report_formatter_chain
    | send_email_to_subscribers
)


def run_pipeline(city: str) -> dict[str, Any]:
    """Execute the LangGraph chain for the given city."""

    return chain.invoke({"city": city})


def run_markdown_report(city: str) -> str:
    """Return the markdown report produced by the pipeline."""

    return run_pipeline(city).get("markdown_report", "")


def run_pipelines_for_cities(
    cities: Sequence[str] = SUPPORTED_CITIES,
) -> dict[str, dict[str, Any]]:
    """Execute one pipeline per city concurrently."""

    ordered_cities = tuple(cities)
    results_by_city: dict[str, dict[str, Any]] = {}

    if not ordered_cities:
        return results_by_city

    with ThreadPoolExecutor(max_workers=len(ordered_cities)) as executor:
        futures = {executor.submit(run_pipeline, city): city for city in ordered_cities}

        for future in as_completed(futures):
            city = futures[future]

            try:
                results_by_city[city] = future.result()
            except Exception as exc:  # noqa: BLE001
                results_by_city[city] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "markdown_report": "",
                }

    return results_by_city


def render_city_reports_markdown(
    results_by_city: Mapping[str, dict[str, Any]],
    cities: Sequence[str] = SUPPORTED_CITIES,
) -> str:
    """Render city pipeline results as a markdown document."""

    sections: list[str] = []

    for city in cities:
        city_result = results_by_city.get(city, {})
        report = city_result.get("markdown_report", "")
        error_message = city_result.get("error")

        sections.append(f"## {city}")

        if error_message:
            sections.append(f"**Error:** `{error_message}`")
        elif report:
            sections.append(report)
        else:
            sections.append("_No markdown report was generated for this city._")

    return "\n\n".join(sections)


def main() -> None:
    """CLI entry point that runs the pipeline and emits markdown."""

    parser = argparse.ArgumentParser(description="Run the NV Local research pipeline.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to save the resulting markdown report.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Skip printing the report to stdout.",
    )

    args = parser.parse_args()
    print(f"Running NV Local pipeline for {', '.join(SUPPORTED_CITIES)} in parallel...")
    results_by_city = run_pipelines_for_cities(SUPPORTED_CITIES)
    report = render_city_reports_markdown(results_by_city, SUPPORTED_CITIES)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report or "", encoding="utf-8")

    if not args.quiet:
        print(report)


if __name__ == "__main__":
    main()
