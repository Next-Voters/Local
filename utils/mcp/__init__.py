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
from utils.mcp.wikidata import (
    get_wikidata_session,
    search_entity,
    get_org_classification,
    analyze_reliability,
)
from utils.mcp.political_figures import (
    get_political_figures_session,
    find_political_figures,
    extract_commentary,
    search_politician_tweets,
)
from utils.mcp.deepl import (
    get_deepl_session,
    managed_deepl_session,
    translate_text,
)

__all__ = [
    # Tavily
    "get_api_key",
    "get_tavily_session",
    "search_legislation",
    "search_political_content",
    "extract_search_results",
    "extract_url_content",
    # Wikidata
    "get_wikidata_session",
    "search_entity",
    "get_org_classification",
    "analyze_reliability",
    # Political Figures
    "get_political_figures_session",
    "find_political_figures",
    "extract_commentary",
    "search_politician_tweets",
    # DeepL
    "get_deepl_session",
    "managed_deepl_session",
    "translate_text",
]
