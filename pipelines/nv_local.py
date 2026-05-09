"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse
from typing import Any

from utils.supabase_client import get_supported_cities_from_db, get_supported_topics
from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.legislation_finder import legislation_finder_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.summary_writer import summary_writer_chain

chain = (
    legislation_finder_chain
    | content_retrieval_chain
    | note_taker_chain.with_retry()
    | summary_writer_chain.with_retry()
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
    args = parser.parse_args()
    label = f"{args.city}" + (f" ({args.topic})" if args.topic else "")
    print(f"Running NV Local pipeline for {label}...")
    result = run_pipeline(args.city, args.topic)
    summary = result.get("legislation_summary")
    if summary and summary.items:
        for item in summary.items:
            print(f"\n{item.header}")
            for bullet in item.bullets:
                print(f"  - {bullet}")
    else:
        print("No legislation items found.")
