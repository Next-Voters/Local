"""CLI output helpers for console display."""

from rich.console import Console
from rich.panel import Panel
from rich import box

console = Console()


def show_welcome():
    """Display welcome message."""
    console.print()
    console.print(
        Panel.fit(
            "[bold red]⚡  NEXT VOTERS LOCAL  ⚡[/bold red]",
            subtitle="[dim]Find your city's legislation[/dim]",
            border_style="red",
            box=box.DOUBLE,
            padding=(1, 4),
        )
    )
    console.print()
    console.print(
        "[red]▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔[/red]"
    )
    console.print()
    console.print(
        "[dim]🔎  Discover recent municipal legislation, by-laws & civic updates[/dim]"
    )
    console.print("  [dim]📜  Stay informed about city council decisions[/dim]")
    console.print("  [dim]🗳️  Empower your local voting decisions[/dim]")
    console.print()
    console.print(
        "[green]▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔[/green]"
    )
    console.print()


def LOG(message: str, style: str = "dim"):
    """Styled logging output."""
    console.print(message, style=style)
