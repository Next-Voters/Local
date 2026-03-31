"""Tavily MCP service — web search (legislation, political content) and URL extraction.

Import from here (or from client.py) for app code. server.py runs as a stdio subprocess.
"""

from utils.mcp.tavily.client import (
    extract_search_results,
    extract_url_content,
    get_api_key,
    get_tavily_session,
    search_legislation,
    search_political_content,
)

__all__ = [
    "get_api_key",
    "get_tavily_session",
    "search_legislation",
    "search_political_content",
    "extract_search_results",
    "extract_url_content",
]