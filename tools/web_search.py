"""Web search tool adapter for legislation discovery.

Searches for legislation via Tavily, then fetches and compresses full page
content for each result URL so the researcher agent can evaluate source
quality directly.  Returns compressed content in the tool message and
pushes ``{"url", "content"}`` dicts to pipeline state.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from config.constants import WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_PER_URL_CHAR_CAP
from tools._helpers import err, ok
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


def _fetch_and_compress(
    urls: list[str],
    url_titles: dict[str, str],
    query: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Batch-fetch URLs via Tavily Extract, then compress each page.

    Returns:
        (compressed_by_url, errors_by_url) — two dicts keyed by URL.
    """
    if not urls:
        return {}, {}

    # Batch extract -------------------------------------------------------
    try:
        raw_by_url = extract_url_content(urls)
    except Exception as exc:
        logger.warning("Tavily Extract failed entirely: %s", exc)
        return {}, {url: str(exc) for url in urls}

    extracted_urls = set(raw_by_url)
    errors_by_url: dict[str, str] = {
        url: "extraction returned no content"
        for url in urls
        if url not in extracted_urls
    }

    # Compress each page in parallel --------------------------------------
    def _compress_one(url: str) -> tuple[str, str]:
        raw = raw_by_url[url]
        if len(raw) > WEB_SEARCH_PER_URL_CHAR_CAP:
            raw = raw[:WEB_SEARCH_PER_URL_CHAR_CAP]
        return url, compress_text(raw, query=query)

    compressed_by_url: dict[str, str] = {}
    compress_targets = [u for u in urls if u in extracted_urls]
    if compress_targets:
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(_compress_one, url): url
                for url in compress_targets
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    _, compressed = future.result()
                    compressed_by_url[url] = compressed
                except Exception as exc:
                    logger.warning("Compression failed for %s: %s", url, exc)
                    # Fall back to capped raw content
                    raw = raw_by_url.get(url, "")
                    if raw:
                        compressed_by_url[url] = raw[:WEB_SEARCH_PER_URL_CHAR_CAP]
                    else:
                        errors_by_url[url] = f"compression failed: {exc}"

    return compressed_by_url, errors_by_url


def _build_tool_message(
    query: str,
    city: str,
    results: list[dict[str, Any]],
    compressed_by_url: dict[str, str],
    errors_by_url: dict[str, str],
) -> str:
    """Build a human-readable tool message with full compressed content."""
    header = (
        f"Web search for '{query}' (city: {city}) "
        f"returned {len(results)} result(s):\n"
    )
    sections: list[str] = []
    for i, result in enumerate(results, start=1):
        url = result["url"]
        title = result["title"]

        if url in compressed_by_url and compressed_by_url[url]:
            sections.append(
                f"--- [{i}] {title} ---\n"
                f"URL: {url}\n"
                f"Content:\n{compressed_by_url[url]}"
            )
        elif url in errors_by_url:
            sections.append(
                f"--- [{i}] {title} ---\n"
                f"URL: {url}\n"
                f"(content extraction failed: {errors_by_url[url]})"
            )
        else:
            sections.append(
                f"--- [{i}] {title} ---\n"
                f"URL: {url}\n"
                f"(no content available)"
            )

    return header + "\n\n".join(sections)


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("region")],
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> Command:
    """Search the web for legislation and return full compressed page content.

    Uses Tavily search with a legislation profile, then fetches and compresses
    each result page so the researcher can evaluate content directly.

    Args:
        query: The search query — e.g. "Austin city council bylaws March 2026".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        max_results: Maximum number of results to return (default 3).

    Returns:
        A Command object that updates the state with search results and content.
    """
    logger.info(
        "web_search called: query=%r city=%r max_results=%d", query, city, max_results
    )
    try:
        raw_results = await asyncio.to_thread(
            search_legislation, query=query, city=city, max_results=max_results
        )

        results = _extract_search_results(raw_results)
        urls = [r["url"] for r in results if r.get("url")]
        url_titles = {r["url"]: r["title"] for r in results if r.get("url")}

        if not urls:
            summary = f"Web search for '{query}' (city: {city}) returned 0 results."
            return ok(tool_call_id, summary, legislation_sources=[])

        # Fetch full page content and compress --------------------------------
        compressed_by_url, errors_by_url = await asyncio.to_thread(
            _fetch_and_compress, urls, url_titles, query
        )

        # Build state: {"url", "content"} dicts for all results ---------------
        legislation_sources: list[dict[str, str]] = []
        for url in urls:
            content = compressed_by_url.get(url, "")
            legislation_sources.append({"url": url, "content": content})

        # Build tool message with full compressed content ---------------------
        summary = _build_tool_message(
            query, city, results, compressed_by_url, errors_by_url
        )

        logger.info(
            "web_search returning %d URLs (%d with content) for city=%r",
            len(urls),
            len(compressed_by_url),
            city,
        )

        return ok(tool_call_id, summary, legislation_sources=legislation_sources)

    except ValueError as e:
        logger.error("web_search ValueError: %s", e)
        return err(tool_call_id, f"Tavily API key not configured: {e}")
    except Exception as e:
        logger.error("web_search failed: %s", e)
        return err(tool_call_id, f"Web search failed: {e}")
