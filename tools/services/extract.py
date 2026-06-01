"""Tavily URL content extraction via the tavily-python SDK.

Sync function using TavilyClient. Used by the web_search tool.
"""

from __future__ import annotations

import os

from tavily import TavilyClient


def extract_url_content(urls: list[str]) -> dict[str, str]:
    """Batch-extract page content for URLs using the Tavily SDK.

    Tavily API limits extraction to 20 URLs per request.
    Only the first 20 URLs are processed.

    Args:
        urls: List of URLs to extract content from.

    Returns:
        Dict mapping URL to extracted content (markdown format).
    """
    if not urls:
        return {}

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY not set in environment. "
            "Get your key at https://app.tavily.com/"
        )

    urls_to_extract = urls[:20]
    client = TavilyClient(api_key=api_key)
    response = client.extract(urls=urls_to_extract, format="markdown")

    return {
        item["url"]: item["raw_content"]
        for item in response.get("results", [])
        if item.get("raw_content")
    }
