"""CLI wrapper script for NV Local voter education tool.

This module is a simple entry point script that runs the CLI main function.
It displays the welcome message, executes the multi-city pipeline,
and renders the resulting markdown report sections.

Usage:
    python run_cli_main.py

This script is an alternative to running `python -m cli.main`.
"""

from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from data import SUPPORTED_CITIES
from runners.run_container_job import (
    render_city_reports_markdown,
    run_pipelines_for_cities,
)
from utils.cli import show_welcome

load_dotenv()

console = Console()

if __name__ == "__main__":
    show_welcome()

    console.print()
    results_by_city = run_pipelines_for_cities(SUPPORTED_CITIES)
    report = render_city_reports_markdown(results_by_city, SUPPORTED_CITIES)

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
