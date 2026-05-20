"""Web search tool adapter for legislation discovery.

Calls Tavily Search to find URLs, then Tavily Extract + compression to
fetch and compress page content inline. The researcher agent receives
full compressed content in its context window.
"""

import asyncio
from typing import Annotated, Any

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from config.constants import WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_PER_URL_CHAR_CAP
from tools._helpers import ok, err
from tools.services.extract import extract_url_content
from tools.services.tavily import search_legislation
from utils.content.compressor import compress_text
from utils.logger import get_logger

logger = get_logger(__name__)


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


def _fetch_and_compress(urls: list[str], query: str) -> dict[str, str]:
    """Batch-extract URLs and compress each page's content.

    Returns a mapping of URL to compressed content. URLs that fail
    extraction or compression are omitted from the result.
    """
    try:
        url_to_content = extract_url_content(urls)
    except Exception as e:
        logger.warning("Tavily Extract failed: %s", e)
        url_to_content = {}

    compressed: dict[str, str] = {}
    for url, raw in url_to_content.items():
        if not raw:
            continue
        capped = raw[:WEB_SEARCH_PER_URL_CHAR_CAP]
        try:
            compressed[url] = compress_text(capped, query=query)
        except Exception:
            logger.warning("Compression failed for %s", url, exc_info=True)
            compressed[url] = capped
    return compressed


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("region")],
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses Tavily search with a legislation profile to prioritize official government
    sites, legislative databases, and authoritative news sources. Fetches and
    compresses page content inline so the researcher can read actual content.

    Args:
        query: The search query — e.g. "Austin city council bylaws March 2026" or
               "municipal ordinance zoning city council passed".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with search results and content.
    """
    logger.info("web_search called: query=%r city=%r max_results=%d", query, city, max_results)
    try:
        raw_results = await asyncio.to_thread(
            search_legislation, query=query, city=city, max_results=max_results
        )

        results = _extract_search_results(raw_results)

        urls = [r["url"] for r in results if r.get("url")]
        if not urls:
            return ok(
                tool_call_id,
                f"Web search for '{query}' (city: {city}) returned 0 result(s).",
                legislation_sources=[],
            )

        compressed = await asyncio.to_thread(_fetch_and_compress, urls, query)

        legislation_sources: list[dict[str, str]] = [
            {"url": url, "content": compressed.get(url, "")}
            for url in urls
        ]

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            url = r["url"]
            title = r["title"]
            content = compressed.get(url)
            if content:
                lines.append(f"--- [{i}] {title} ---\nURL: {url}\nContent:\n{content}")
            else:
                lines.append(f"--- [{i}] {title} ---\nURL: {url}\n(content extraction failed)")

        summary = (
            f"Web search for '{query}' (city: {city}) returned "
            f"{len(urls)} result(s):\n\n"
            + "\n\n".join(lines)
        )
        logger.info("web_search returning %d URLs for city=%r", len(urls), city)

        return ok(tool_call_id, summary, legislation_sources=legislation_sources)

    except ValueError as e:
        logger.error("web_search ValueError: %s", e)
        return err(tool_call_id, f"Tavily API key not configured: {e}")
    except Exception as e:
        logger.error("web_search failed: %s", e)
        return err(tool_call_id, f"Web search failed: {e}")
