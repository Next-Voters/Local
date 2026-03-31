"""Tavily MCP server — runs as a standalone stdio subprocess.

This file is NOT imported by app code. It is launched by client.py as a
subprocess. Provides FastMCP tools wrapping the tavily-python SDK for
generic and profile-aware search plus content extraction.

Usage: python -m utils.mcp.tavily.server
"""

import os
from pathlib import Path
from typing import Any

import yaml
from fastmcp import FastMCP
from tavily import TavilyClient

mcp = FastMCP("Tavily")

_PROFILES_DIR = Path(__file__).parent.parent.parent / "config" / "search_profiles"


def _get_client() -> TavilyClient:
    return TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))


@mcp.tool
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


@mcp.tool
def tavily_extract(urls: list[str]) -> dict:
    """Extract full page content from a list of URLs.

    Args:
        urls: URLs to extract content from.

    Returns:
        Dict with "results" (successful) and "failed_results" (failed) lists.
    """
    client = _get_client()
    return client.extract(urls=urls, format="markdown")


# ---------------------------------------------------------------------------
# Profile-based search helpers (moved from tavily_client.py)
# ---------------------------------------------------------------------------


def _load_search_profile(profile_name: str) -> dict[str, Any]:
    """Load search profile config from YAML file."""
    config_path = _PROFILES_DIR / f"{profile_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Search profile not found: {config_path}")
    with open(config_path) as f:
        profile = yaml.safe_load(f)
    return profile if isinstance(profile, dict) else {}


def _render_terms(terms: list[str], city: str | None) -> list[str]:
    rendered = []
    for term in terms:
        if not isinstance(term, str):
            continue
        rendered.append(term.format(city=city or ""))
    return rendered


def _build_query(query: str, city: str | None, profile: dict[str, Any]) -> str:
    base_query = query.strip()
    prefix = str(profile.get("query_prefix", "")).strip()
    suffix = str(profile.get("query_suffix", "")).strip()
    required_terms = _render_terms(profile.get("required_terms", []), city)
    excluded_terms = _render_terms(profile.get("excluded_terms", []), city)

    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(base_query)
    if city and profile.get("append_city", True):
        parts.append(f'"{city}"')
    if suffix:
        parts.append(suffix)
    parts.extend(required_terms)
    parts.extend(f"-{term}" for term in excluded_terms if term)

    return " ".join(p for p in parts if p)


def _search_with_profile(
    query: str,
    profile_name: str,
    max_results: int = 10,
    city: str | None = None,
) -> dict:
    """Search Tavily using a named search profile."""
    profile = _load_search_profile(profile_name)
    client = _get_client()

    kwargs: dict[str, Any] = {
        "query": _build_query(query=query, city=city, profile=profile),
        "max_results": min(max_results, int(profile.get("max_results_cap", 20))),
        "search_depth": profile.get("search_depth", "basic"),
        "topic": profile.get("topic", "general"),
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
    }

    include_domains = profile.get("include_domains", [])
    exclude_domains = profile.get("exclude_domains", [])
    if isinstance(include_domains, list) and include_domains:
        kwargs["include_domains"] = include_domains
    if isinstance(exclude_domains, list) and exclude_domains:
        kwargs["exclude_domains"] = exclude_domains

    days = profile.get("days")
    if isinstance(days, int) and days > 0:
        kwargs["days"] = days

    return client.search(**kwargs)


# ---------------------------------------------------------------------------
# Profile-aware MCP tools
# ---------------------------------------------------------------------------


@mcp.tool
def search_legislation(
    query: str,
    city: str,
    max_results: int = 5,
) -> dict:
    """Search for legislation using the legislation search profile.

    Uses Tavily with a legislation profile that prioritizes official government
    sites, legislative databases, and authoritative news sources.

    Args:
        query: The search query for legislation.
        city: The city to find legislation for.
        max_results: Maximum number of results to return.

    Returns:
        Dict with Tavily search results.
    """
    return _search_with_profile(
        query=query,
        profile_name="legislation",
        max_results=max_results,
        city=city,
    )


@mcp.tool
def search_political_content(
    query: str,
    city: str | None = None,
    max_results: int = 5,
) -> dict:
    """Search for political content using the political search profile.

    Uses Tavily with a political profile that emphasizes official and
    major-news sources for political commentary.

    Args:
        query: The search query for political content.
        city: Optional city name for local context.
        max_results: Maximum number of results to return.

    Returns:
        Dict with Tavily search results.
    """
    return _search_with_profile(
        query=query,
        profile_name="political",
        max_results=max_results,
        city=city,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
