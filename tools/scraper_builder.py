"""Tools for the Scraper Builder agent (Agent 2).

Contains: Code generator, Python REPL, Debugger.
All tools return Command objects to update LangGraph state.
"""


from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import InjectedState

from langgraph.types import Command

@tool
def code_generator(
    final_legislation_sources: Annotated[list[BaseMessage], InjectedState("final_legislation_sources")],
) -> Command:
    """Generate Python scraping code based on URLs and bill metadata.

    Takes a list of URLs and metadata about the bills/legislation to scrape,
    and generates executable Python code for extracting the relevant data.

    Args:
        urls: List of URLs to scrape legislation from.
        bill_metadata: Dictionary containing metadata about bills
                      (e.g., title, date range, target fields).

    Returns:
        A Command that updates the graph state with generated_scraper_code.
    """



@tool
def python_repl(
    scraper_code: str,
) -> Command:
    """Execute Python code in a sandboxed environment.

    Takes generated scraping code and executes it, returning the raw results.

    Args:
        scraper_code: The Python code to execute.

    Returns:
        A Command that updates the graph state with raw_scrape_results.
    """
    pass

@tool
def debugger(
    scraper_code: str,
    error_message: str,
) -> Command:
    """Debug and fix scraper code based on error messages.

    Takes the current scraper code and an error message, and generates
    corrected code that addresses the issue.

    Args:
        scraper_code: The current (broken) scraper code.
        error_message: The error message or traceback from execution.

    Returns:
        A Command that updates the graph state with corrected_scraper_code.
    """
    pass
