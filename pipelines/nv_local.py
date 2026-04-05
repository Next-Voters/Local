"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from utils.supabase_client import get_supported_cities_from_db, get_supported_topics
from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.email_sender import email_sender_chain
from pipelines.node.legislation_finder import legislation_finder_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.report_formatter import report_formatter_chain
from pipelines.node.summary_writer import summary_writer_chain

# Pipeline chain without email_sender (email dispatch happens separately)
chain = (
    legislation_finder_chain
    | content_retrieval_chain
    | note_taker_chain.with_retry()
    | summary_writer_chain.with_retry()
    | report_formatter_chain
    # Note: email_sender_chain is removed from the main pipeline
    # Email dispatch now happens in a separate batch operation via email_dispatcher.py
)


def run_pipeline(city: str, topic: str = "") -> dict[str, Any]:
    """Execute the LangGraph chain for the given city and topic."""

    return chain.invoke({"city": city, "topic": topic})


def main() -> None:
    """Entry point that runs the pipeline for one city."""

    # Get supported cities from Supabase
    try:
        cities = get_supported_cities_from_db()
    except Exception as e:
        print(f"Error: Failed to get supported cities from Supabase: {e}")
        raise

    parser = argparse.ArgumentParser(description="Run the NV Local research pipeline.")
    parser.add_argument(
        "city",
        choices=cities,
        help="City to run the NV Local pipeline for.",
    )
    # Load supported topics for CLI choices
    try:
        topics = get_supported_topics()
    except Exception as e:
        print(f"Error: Failed to get supported topics from Supabase: {e}")
        raise

    parser.add_argument(
        "-t",
        "--topic",
        choices=topics,
        default="",
        help="Topic to scope the pipeline research to.",
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
    label = f"{args.city}" + (f" ({args.topic})" if args.topic else "")
    print(f"Running NV Local pipeline for {label}...")
    result = run_pipeline(args.city, args.topic)
    report = result.get("markdown_report", "")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report or "", encoding="utf-8")

    if not args.quiet:
        print(report)
