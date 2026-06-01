"""Shared helpers for agent invocation utilities.

Kept in a separate module to avoid circular imports — the invoke_*
modules import from here, and ``__init__.py`` re-exports.
"""

from __future__ import annotations


def reconcile_sources(
    accumulated: list[str | dict],
    curated_urls: list[str],
) -> list[str | dict]:
    """Match curated URL list against accumulated content dicts.

    Agent state accumulates both ``{"url", "content"}`` dicts (from
    ``web_search``) and plain URL strings (from ``handoff`` / structured
    output).  The *curated_urls* represent the agent's selected subset.

    Returns only the curated URLs, enriched with content where available.
    If *curated_urls* is empty (e.g. recursion-limit exit before handoff),
    returns all dict items from *accumulated* as a fallback.
    """
    # Build content lookup from dict items
    content_by_url: dict[str, str] = {}
    for source in accumulated:
        if isinstance(source, dict):
            url = source.get("url", "")
            content = source.get("content", "")
            if url and content:
                content_by_url[url] = content

    # If no curated list, fall back to all dicts
    if not curated_urls:
        return [
            s for s in accumulated
            if isinstance(s, dict) and s.get("url")
        ]

    # Enrich curated URLs with content
    result: list[str | dict] = []
    seen: set[str] = set()
    for url in curated_urls:
        if url in seen:
            continue
        seen.add(url)
        if url in content_by_url:
            result.append({"url": url, "content": content_by_url[url]})
        else:
            result.append(url)

    return result
