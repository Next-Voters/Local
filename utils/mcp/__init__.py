"""MCP client utilities for connecting to external services.

Each subdirectory is a self-contained MCP service with two files:
  - client.py: The interface app code imports. Connects to the server via stdio subprocess.
  - server.py: The FastMCP server that runs as a standalone subprocess. Not imported directly.
"""

from utils.mcp.tavily import (
    get_api_key,
    get_tavily_session,
    search_legislation,
    search_political_content,
    extract_search_results,
    extract_url_content,
)

__all__ = [
    # Tavily
    "get_api_key",
    "get_tavily_session",
    "search_legislation",
    "search_political_content",
    "extract_search_results",
    "extract_url_content",
]
