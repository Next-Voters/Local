"""Tools for the Political Commentry Agent (Agent 2).

Contains: political_figure_finder, blog_search.
All tools return Command objects to update LangGraph state.
"""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.tools import (
    detect_country_from_city,
    fetch_canadian_political_figures,
    fetch_american_political_figures,
)


@tool
def political_figure_finder(
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
) -> Command:
    """Find political figures (candidates, elected officials) for a specific city.

    Queries an external data service to find Canadian and American political
    candidates and elected officials for the given city. The country is
    automatically detected using geocoding.

    Args:
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city name to search for political figures (injected from state).

    Returns:
        A Command object that updates the state with political figure data.
    """
    try:
        country_code = detect_country_from_city(city)
    except Exception as e:
        return Command(
            update={
                "political_figures": [],
                "messages": [
                    ToolMessage(
                        content=f"Failed to detect country for city '{city}': {e}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    if country_code not in ("CA", "US"):
        return Command(
            update={
                "political_figures": [],
                "messages": [
                    ToolMessage(
                        content=f"Unsupported country: {country_code}. Only Canada (CA) and USA (US) are supported.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    country = "canada" if country_code == "CA" else "usa"

    try:
        if country == "canada":
            political_figures = fetch_canadian_political_figures(city)
        else:
            political_figures = fetch_american_political_figures(city)

        summary_lines = [
            f"Found {len(political_figures)} political figure(s) in {city}, {country}:"
        ]
        for pf in political_figures:
            summary_lines.append(
                f"  - {pf['name']} ({pf.get('position', 'Unknown position')})"
            )

        return Command(
            update={
                "political_figures": political_figures,
                "country": country,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        error_msg = f"Failed to find political figures: {e}"
        return Command(
            update={
                "political_figures": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


@tool
def blog_search(
    political_figure_name: Annotated[str, InjectedState("current_political_figure")],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: int = 5,
) -> Command:
    """Search for a political figure's blog or personal website.

    Placeholder tool — searches for official blogs, websites, and campaign
    sites for a given political figure.

    Args:
        political_figure_name: Name of the political figure to search for.
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with blog URLs.
    """
    # TODO: Implement blog search via SerpAPI or similar
    # Should prioritize official domains, campaign sites, and known blog platforms
    pass
