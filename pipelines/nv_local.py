"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.email_sender import email_sender_chain
from pipelines.node.legislation_finder import legislation_finder_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.politician_commentary import politician_commentary_chain
from pipelines.node.report_formatter import report_formatter_chain
from pipelines.node.summary_writer import summary_writer_chain
from data import SUPPORTED_CITIES

chain = (
    legislation_finder_chain
    | content_retrieval_chain
    | note_taker_chain.with_retry()
    | summary_writer_chain.with_retry()
    | politician_commentary_chain
    | report_formatter_chain
    | email_sender_chain
)


def run_pipeline(city: str) -> dict[str, Any]:
    """Execute the LangGraph chain for the given city."""

    return chain.invoke({"city": city})


def main() -> None:
    """Entry point that runs the pipeline for one city."""

    parser = argparse.ArgumentParser(description="Run the NV Local research pipeline.")
    parser.add_argument(
        "city",
        choices=SUPPORTED_CITIES,
        help="City to run the NV Local pipeline for.",
    )
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
    print(f"Running NV Local pipeline for {args.city}...")
    result = run_pipeline(args.city)
    report = result.get("markdown_report", "")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report or "", encoding="utf-8")

    if not args.quiet:
        print(report)
