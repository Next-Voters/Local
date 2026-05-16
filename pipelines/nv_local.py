"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse
from typing import Any

from utils.supabase_client import get_supported_regions_from_db
from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.run_agent_team import run_agent_team_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.summary_writer import summary_writer_chain

chain = (
    run_agent_team_chain
    | content_retrieval_chain
    | note_taker_chain
    | summary_writer_chain
)


def run_pipeline(region: str) -> dict[str, Any]:
    """Execute the pipeline for the given region across all topics.

    Topics are fetched from Supabase inside the legislation_finder node.

    Args:
        region: Region name (must be in Supabase regions table).

    Returns:
        ChainData dict with ``topic_results`` containing per-topic outputs.
    """
    return chain.invoke({"region": region})


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
    args = parser.parse_args()

    print(f"Running NV Local pipeline for {args.region} (all topics)...")
    result = run_pipeline(args.region)

    # Print per-topic results
    topic_results = result.get("topic_results", {})
    for topic, topic_data in topic_results.items():
        print(f"\n{'='*60}")
        print(f"Topic: {topic}")
        print(f"{'='*60}")
        summary = topic_data.get("legislation_summary")
        if summary and summary.items:
            for item in summary.items:
                print(f"\n{item.header}")
                for bullet in item.bullets:
                    print(f"  - {bullet}")
        else:
            print("No legislation items found.")
