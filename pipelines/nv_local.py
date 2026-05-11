"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse
from typing import Any

from utils.supabase_client import get_supported_regions_from_db, get_supported_topics
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


def run_pipeline(region: str, topic: str = "") -> dict[str, Any]:
    """Execute the LangGraph chain for the given region and topic."""

    return chain.invoke({"region": region, "topic": topic})


def main() -> None:
    """Entry point that runs the pipeline for one city."""

    # Get supported regions from Supabase
    try:
        regions = get_supported_regions_from_db()
    except Exception as e:
        print(f"Error: Failed to get supported regions from Supabase: {e}")
        raise

    parser = argparse.ArgumentParser(description="Run the NV Local research pipeline.")
    parser.add_argument(
        "region",
        choices=regions,
        help="Region to run the NV Local pipeline for.",
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
    label = f"{args.region}" + (f" ({args.topic})" if args.topic else "")
    print(f"Running NV Local pipeline for {label}...")
    result = run_pipeline(args.region, args.topic)
    summary = result.get("legislation_summary")
    if summary and summary.items:
        for item in summary.items:
            print(f"\n{item.header}")
            for bullet in item.bullets:
                print(f"  - {bullet}")
    else:
        print("No legislation items found.")
