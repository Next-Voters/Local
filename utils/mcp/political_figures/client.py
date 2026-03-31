"""Political Figures MCP client — the interface app code imports.

Launches server.py as a stdio subprocess and exposes async functions for
finding political figures, extracting commentary, and searching tweets.
Do not run this file directly; import its functions from your application.

Usage:
    result = await find_political_figures(city="Toronto")
    extraction = await extract_commentary(url="...", politician="...", query="...")
    tweets = await search_politician_tweets(politician_name="...", city="...")
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from utils.mcp._shared import parse_mcp_result

_SERVER_PATH = str(Path(__file__).parent / "server.py")


@asynccontextmanager
async def get_political_figures_session():
    """Get MCP session connected to the local political figures server via stdio.

    Launches political_figures_server.py as a subprocess and communicates
    via stdin/stdout. Session is properly cleaned up on exit.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_SERVER_PATH],
        env={**os.environ},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def find_political_figures(city: str) -> dict[str, Any]:
    """Find political figures for a city.

    Args:
        city: The city name to search for political figures.

    Returns:
        Dict with "figures" (list) and "country" ("canada" or "usa").
    """
    async with get_political_figures_session() as session:
        result = await session.call_tool(
            "find_political_figures", {"city": city}
        )
        return parse_mcp_result(result)


async def extract_commentary(
    url: str, politician: str, query: str
) -> dict[str, Any]:
    """Extract political commentary from a web page.

    Args:
        url: The URL to extract commentary from.
        politician: The politician to find commentary for.
        query: The search query context.

    Returns:
        Dict with "commentary" key.
    """
    async with get_political_figures_session() as session:
        result = await session.call_tool(
            "extract_commentary",
            {"url": url, "politician": politician, "query": query},
        )
        return parse_mcp_result(result)


async def search_politician_tweets(
    politician_name: str,
    city: str = "",
    research_context: str = "",
    max_results: int = 10,
) -> dict[str, Any]:
    """Search for a politician's tweets on Twitter/X.

    Args:
        politician_name: The full name of the politician.
        city: City to filter tweets by.
        research_context: Additional context for filtering.
        max_results: Maximum number of tweets.

    Returns:
        Dict with "user_found", "tweets", and optional "error".
    """
    async with get_political_figures_session() as session:
        result = await session.call_tool(
            "search_politician_tweets",
            {
                "politician_name": politician_name,
                "city": city,
                "research_context": research_context,
                "max_results": max_results,
            },
        )
        return parse_mcp_result(result)
