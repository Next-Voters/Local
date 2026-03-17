from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from pipelines.nv_local import chain
from utils.cli import show_welcome, LOG

console = Console()

if __name__ == "__main__":
    show_welcome()

    city = input("\n➜ Enter city name: ")

    console.print()
    result = chain.invoke({"city": city})

    report = result.get("markdown_report")

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
