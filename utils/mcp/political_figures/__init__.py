"""Political Figures MCP service — find politicians, extract commentary, search tweets.

Import from here (or from client.py) for app code. server.py runs as a stdio subprocess.
"""

from utils.mcp.political_figures.client import (
    extract_commentary,
    find_political_figures,
    get_political_figures_session,
    search_politician_tweets,
)

__all__ = [
    "get_political_figures_session",
    "find_political_figures",
    "extract_commentary",
    "search_politician_tweets",
]