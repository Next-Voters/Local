"""Tavily MCP client — the interface app code imports.

Launches server.py as a stdio subprocess and exposes async functions for
legislation search, political content search, and URL content extraction.
Do not run this file directly; import its functions from your application.

Profile logic (query building, domain filters) lives in server.py.
Content extraction uses the tavily-python SDK directly.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from tavily import AsyncTavilyClient

from utils.mcp.session import MCPSessionManager

_SERVER_PATH = str(Path(__file__).parent / "server.py")


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def get_api_key() -> str:
    """Get Tavily API key from environment."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY not set in environment. "
            "Get your key at https://app.tavily.com/"
        )
    return api_key


# ---------------------------------------------------------------------------
# MCP session (stdio subprocess)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_tavily_session():
    """Get MCP session connected to the local Tavily server via stdio.

    Launches tavily_server.py as a subprocess and communicates via stdin/stdout.
    Session is properly cleaned up on exit.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_SERVER_PATH],
        env={**os.environ, "TAVILY_API_KEY": get_api_key()},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


_manager = MCPSessionManager("tavily_session", get_tavily_session)
managed_tavily_session = _manager.managed_session


# ---------------------------------------------------------------------------
# Search (via MCP — profile logic is now in the server)
# ---------------------------------------------------------------------------

async def search_legislation(
    query: str,
    city: str,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search for legislation using the legislation profile."""
    return await _manager.call_tool(
        "search_legislation", {"query": query, "city": city, "max_results": max_results}
    )


async def search_political_content(
    query: str,
    city: str | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search political content using the political profile."""
    args: dict[str, Any] = {"query": query, "max_results": max_results}
    if city is not None:
        args["city"] = city
    return await _manager.call_tool("search_political_content", args)


# ---------------------------------------------------------------------------
# Result extraction helpers
# ---------------------------------------------------------------------------

def extract_search_results(raw_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract title/url/description/score from Tavily results.

    Results are returned in the order Tavily (or the profile layer) provides
    them — typically sorted by relevance score descending.
    """
    results: list[dict[str, Any]] = []

    if isinstance(raw_results, dict):
        tavily_results = raw_results.get("results", [])
        if isinstance(tavily_results, list):
            for result in tavily_results:
                if not isinstance(result, dict):
                    continue
                results.append(
                    {
                        "title": str(result.get("title") or "Untitled"),
                        "url": str(result.get("url") or ""),
                        "description": str(result.get("content") or ""),
                        "score": float(result.get("score", 0.0)),
                    }
                )

    return results


# ---------------------------------------------------------------------------
# Extract (via tavily-python SDK — no MCP equivalent yet)
# ---------------------------------------------------------------------------

async def extract_url_content(urls: list[str]) -> dict[str, str]:
    """Batch-extract page content for URLs using Tavily SDK.

    Tavily API limits extraction to 20 URLs per request. Only the first 20 URLs are processed.

    Returns: dict mapping URL to extracted content (markdown format).
    """
    if not urls:
        return {}

    # Tavily API has a hard limit of 20 URLs per extraction request
    urls_to_extract = urls[:20]

    client = AsyncTavilyClient(api_key=get_api_key())
    response = await client.extract(urls=urls_to_extract, format="markdown")

    return {
        item["url"]: item["raw_content"]
        for item in response.get("results", [])
        if item.get("raw_content")
    }