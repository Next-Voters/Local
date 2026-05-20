"""NV Local single-city pipeline entry points."""

from __future__ import annotations

import argparse

from utils.supabase_client import get_supported_regions_from_db
from pipelines.node.run_agent_team import run_agent_team_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.summary_writer import summary_writer_chain

chain = (
    run_agent_team_chain
    | note_taker_chain
    | summary_writer_chain
)

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

    chain.invoke({"region": args.region})
