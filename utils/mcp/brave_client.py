"""Smithery Brave Search MCP client using official mcp Python SDK.

This module provides a clean connection to the Smithery-hosted Brave Search MCP server
using the official Anthropic MCP Python SDK.

Usage:
    async with get_brave_session() as session:
        result = await session.call_tool("brave_web_search", {...})
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from utils.mcp._shared import parse_mcp_result

SMITHERY_BRAVE_SEARCH_URL = "https://server.smithery.ai/@thomasvan/mcp-brave-search/mcp"


def get_api_key() -> str:
    """Get Brave Search API key from environment."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        raise ValueError(
            "BRAVE_SEARCH_API_KEY not set in environment. "
            "Get your API key at https://api-dashboard.search.brave.com/"
        )
    return api_key


def load_goggles(config_name: str) -> str:
    """Load Goggles rules from YAML config file.

    Args:
        config_name: Name of the config (e.g., 'legislation', 'political')

    Returns:
        Goggles rules as newline-separated string
    """
    config_path = (
        Path(__file__).parent.parent.parent
        / "config"
        / "goggles"
        / f"{config_name}.yaml"
    )

    if not config_path.exists():
        raise FileNotFoundError(f"Goggles config not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return "\n".join(config["rules"])


@asynccontextmanager
async def get_brave_session():
    """Get MCP session connected to Smithery-hosted Brave Search.

    Creates a fresh session each time - no global state.
    Session is properly cleaned up on exit.

    Yields:
        ClientSession: MCP session for calling Brave Search tools
    """
    api_key = get_api_key()

    async with streamable_http_client(
        SMITHERY_BRAVE_SEARCH_URL, headers={"Authorization": f"Bearer {api_key}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def search_with_goggles(
    query: str,
    goggles: str,
    max_results: int = 10,
    country: str = "US",
    freshness: str = "pm",
) -> dict[str, Any]:
    """Search using Brave Search MCP with Goggles for fine-tuned results.

    Args:
        query: The search query string.
        goggles: Goggles rules string.
        max_results: Maximum number of results (1-20).
        country: Country code for localized results.
        freshness: Time filter ('pw', 'pm', 'py').

    Returns:
        Dict with search results.
    """
    async with get_brave_session() as session:
        result = await session.call_tool(
            "brave_web_search",
            {
                "query": query,
                "count": min(max_results, 20),
                "country": country,
                "freshness": freshness,
                "goggles": [goggles],
            },
        )

        return parse_mcp_result(result)


async def search_legislation(
    query: str,
    city: str,
    max_results: int = 5,
    country: str = "US",
) -> dict[str, Any]:
    """Search for legislation using the provided query with Goggles.

    Args:
        query: The search query from the LLM.
        city: The city name for context.
        max_results: Maximum number of results.
        country: Country code for localized results.

    Returns:
        Dict with search results.
    """
    goggles = load_goggles("legislation")

    return await search_with_goggles(
        query=query,
        goggles=goggles,
        max_results=max_results,
        country=country,
        freshness="pm",
    )


async def search_political_content(
    query: str,
    city: str | None = None,
    max_results: int = 5,
    country: str = "US",
) -> dict[str, Any]:
    """Search for political content using the provided query with Goggles.

    Args:
        query: The search query from the LLM.
        city: Optional city name for local context.
        max_results: Maximum number of results.
        country: Country code for localized results.

    Returns:
        Dict with search results.
    """
    goggles = load_goggles("political")

    return await search_with_goggles(
        query=query,
        goggles=goggles,
        max_results=max_results,
        country=country,
    )


def extract_search_results(raw_results: dict) -> list[dict]:
    """Extract relevant fields from Brave Search results.

    Args:
        raw_results: Raw response from Brave Search MCP.

    Returns:
        List of dicts with title, url, and description.
    """
    results = []

    if isinstance(raw_results, dict):
        web_results = raw_results.get("web", {}).get("results", [])
        for result in web_results:
            results.append(
                {
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "description": result.get("description"),
                }
            )

    return results
