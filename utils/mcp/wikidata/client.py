"""Wikidata MCP client — the interface app code imports.

Launches server.py as a stdio subprocess and exposes async functions for
entity search, org classification, and source reliability analysis.
Do not run this file directly; import its functions from your application.

Usage:
    result = await analyze_reliability(sources=[...], city="Toronto")
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from utils.mcp.session import MCPSessionManager

_SERVER_PATH = str(Path(__file__).parent / "server.py")


@asynccontextmanager
async def get_wikidata_session():
    """Get MCP session connected to the local Wikidata server via stdio.

    Launches wikidata_server.py as a subprocess and communicates via stdin/stdout.
    Session is properly cleaned up on exit.
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


_manager = MCPSessionManager("wikidata_session", get_wikidata_session)
managed_wikidata_session = _manager.managed_session


async def search_entity(query: str) -> str | None:
    """Search for a Wikidata entity ID by name.

    Args:
        query: The entity name to search for.

    Returns:
        The entity ID string, or None if not found.
    """
    result = await _manager.call_tool("search_entity", {"query": query})
    return result.get("entity_id")


async def get_org_classification(entity_id: str) -> dict[str, Any]:
    """Get structured organization classification from Wikidata.

    Args:
        entity_id: A valid Wikidata entity ID.

    Returns:
        Dict with label, description, instance_of, country, etc.
    """
    return await _manager.call_tool("get_org_classification", {"entity_id": entity_id})


async def analyze_reliability(
    sources: list[dict[str, Any]], city: str
) -> dict[str, Any]:
    """Analyze source reliability using Wikidata + LLM judgment.

    Args:
        sources: List of dicts with "url" and "organization" keys.
        city: The city to evaluate sources against.

    Returns:
        Dict with "judgments" list.
    """
    return await _manager.call_tool("analyze_reliability", {"sources": sources, "city": city})