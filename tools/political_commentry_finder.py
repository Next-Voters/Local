"""Tools for the Political Commentry Agent (Agent 2).

Contains: political_figure_finder, search_political_commentary.
All tools return Command objects to update LangGraph state.

Uses the official Brave Search MCP server (via Smithery) with Goggles.
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
from utils.mcp.brave_client import search_political_content, extract_search_results


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
async def search_political_commentary(
    query: str,
    city: Annotated[str, InjectedState("city")],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: int = 5,
) -> Command:
    """Search for political commentary using the provided query.

    Uses Brave Web Search MCP with Goggles to find authoritative political
    content. Prioritizes government sites, news sources, and political reference
    sites while filtering out social media and blogs.

    Args:
        query: The search query — e.g. "Austin mayor political commentary" or
               "John Smith city council news opinion".
        city: The city context for local political content (from state).
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with commentary sources.
    """
    try:
        raw_results = await search_political_content(
            query=query,
            city=city,
            max_results=max_results,
        )

        results = extract_search_results(raw_results)

        if not results:
            return Command(
                update={
                    "commentary_sources": [],
                    "messages": [
                        ToolMessage(
                            content=f"No political commentary found for query '{query}'.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        summary_lines = [
            f"Found {len(results)} commentary source(s) for query '{query}':"
        ]
        for r in results:
            summary_lines.append(f"  - {r['title']}: {r['url']}")

        return Command(
            update={
                "commentary_sources": results,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except ValueError as e:
        error_msg = f"Brave Search API key not configured: {e}"
        return Command(
            update={
                "commentary_sources": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )
    except Exception as e:
        error_msg = f"Failed to search political commentary: {e}"
        return Command(
            update={
                "commentary_sources": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )

@tool
def retrieve_commentary_content(
    commentry_sources: Annotated[str, InjectedState("commentry_sources")],
):
    pass