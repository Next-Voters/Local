"""Web search tool adapter for legislation discovery.

Thin adapter that calls Tavily search functions and wraps results
in LangGraph Commands for state updates.  Returns URLs only — content
fetching and PDF extraction are handled downstream by content_retrieval.
"""

import asyncio
import logging
from typing import Annotated, Any

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from config.constants import WEB_SEARCH_MAX_RESULTS
from tools._helpers import ok, err
from tools.services.tavily import search_legislation

logger = logging.getLogger(__name__)


def _extract_search_results(raw_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract title/url/description/score from Tavily results.

    Results are returned in the order Tavily provides them —
    typically sorted by relevance score descending.
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


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("region")],
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses Tavily search with a legislation profile to prioritize official government
    sites, legislative databases, and authoritative news sources.

    Args:
        query: The search query — e.g. "Austin city council bylaws March 2026" or
               "municipal ordinance zoning city council passed".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with search results.
    """
    logger.info("web_search called: query=%r city=%r max_results=%d", query, city, max_results)
    try:
        raw_results = await asyncio.to_thread(
            search_legislation, query=query, city=city, max_results=max_results
        )

        results = _extract_search_results(raw_results)

        legislation_sources: list[str] = []
        for result in results:
            url = result.get("url", "")
            if url:
                legislation_sources.append(url)

        summary_lines = [f"  - {url}" for url in legislation_sources]
        summary = (
            f"Web search for '{query}' (city: {city}) returned "
            f"{len(legislation_sources)} result(s):\n"
            + "\n".join(summary_lines)
        )
        logger.info("web_search returning %d URLs for city=%r", len(legislation_sources), city)

        return ok(tool_call_id, summary, legislation_sources=legislation_sources)

    except ValueError as e:
        logger.error("web_search ValueError: %s", e)
        return err(tool_call_id, f"Tavily API key not configured: {e}")
    except Exception as e:
        logger.error("web_search failed: %s", e)
        return err(tool_call_id, f"Web search failed: {e}")
