"""CLI wrapper script for NV Local voter education tool.

This module is a simple entry point script that runs the CLI main function.
It displays the welcome message, executes the multi-city pipeline,
and renders the resulting markdown report sections.

Usage:
    python run_cli_main.py

This script is an alternative to running `python -m cli.main`.
"""

import logging

from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from utils.supabase_client import get_supported_cities_from_db
from runners.run_container_job import (
    render_city_reports_markdown,
    run_pipelines_for_cities,
)
from utils.cli import show_welcome

load_dotenv()

# Configure logging for CLI output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

console = Console()


def main() -> int:
    """Run the CLI pipeline for all supported cities.

    Returns:
        0 on success, 1 on error
    """
    try:
        show_welcome()

        console.print()

        # Get supported cities from Supabase with error handling
        try:
            cities = get_supported_cities_from_db()
        except Exception as e:
            logger.error(f"Failed to get supported cities: {e}")
            console.print(
                f"[bold red]Error:[/bold red] Could not load supported cities from Supabase: {e}",
            )
            return 1

        if not cities:
            logger.warning("No supported cities found")
            console.print(
                "[bold yellow]Warning:[/bold yellow] No supported cities found"
            )
            return 1

        logger.info(f"Running pipeline for {len(cities)} cities")
        results_by_city = run_pipelines_for_cities(cities)
        report = render_city_reports_markdown(results_by_city, cities)

        console.print()
        console.print(
            Panel.fit(
                "[bold red]NV Local Results[/bold red]",
                border_style="red",
                box=box.DOUBLE,
            )
        )
        console.print()
        console.print(Markdown(report))

        return 0

    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted by user[/bold red]")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
