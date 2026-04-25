"""Tavily search functions — direct SDK calls.

All functions are synchronous (use TavilyClient).
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()
from tavily import TavilyClient

_MIN_SCORE = 0.15
_MAX_RESULTS_CAP = 20

_EXCLUDE_DOMAINS = [
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "medium.com",
    "substack.com",
    "quora.com",
    "youtube.com",
    "wikipedia.org",
    "change.org",
    "petition.parliament.uk",
    "yelp.com",
    "nextdoor.com",
    "patch.com",
    "blogspot.com",
    "wordpress.com",
    "tumblr.com",
]


def _get_client() -> TavilyClient:
    """Return a TavilyClient using the TAVILY_API_KEY env var."""
    return TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))


def tavily_search(
    query: str,
    max_results: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
    days: int | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict:
    """Search the web using Tavily.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.
        search_depth: Search depth — "basic" or "advanced".
        topic: Topic type — "general", "news", or "finance".
        days: Restrict results to the last N days.
        include_domains: Only include results from these domains.
        exclude_domains: Exclude results from these domains.
    """
    client = _get_client()
    kwargs: dict = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
    }
    if days is not None:
        kwargs["days"] = days
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains

    return client.search(**kwargs)


def search_legislation(
    query: str,
    city: str,
    max_results: int = 5,
) -> dict:
    """Search for municipal legislation via Tavily.

    Appends the city name to the query, uses advanced search depth with
    general topic (to include government sites and legislative databases),
    filters by score, and excludes low-quality domains.

    Args:
        query: The search query for legislation.
        city: The city to find legislation for.
        max_results: Maximum number of results to return.

    Returns:
        Dict with Tavily search results.
    """
    client = _get_client()

    fetch_count = min(max_results * 2, _MAX_RESULTS_CAP)

    kwargs: dict[str, Any] = {
        "query": f'{query} "{city}"',
        "max_results": fetch_count,
        "search_depth": "advanced",
        "topic": "general",
        "time_range": "month",
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "exclude_domains": _EXCLUDE_DOMAINS,
    }

    raw = client.search(**kwargs)

    results = raw.get("results", [])
    raw_count = len(results)
    if results:
        scores = [float(r.get("score", 0)) for r in results]
        logger.info(
            "Tavily returned %d raw results for query=%r city=%r; scores=%s",
            raw_count, query, city, scores,
        )
        results.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
        results = [r for r in results if float(r.get("score", 0)) >= _MIN_SCORE]
        logger.info(
            "After score filter (>= %.2f): %d/%d results remain",
            _MIN_SCORE, len(results), raw_count,
        )
        results = results[:max_results]
        raw["results"] = results
    else:
        logger.warning("Tavily returned 0 results for query=%r city=%r", query, city)

    return raw
