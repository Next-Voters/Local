"""Wikidata MCP service — entity lookup, org classification, and source reliability analysis.

Import from here (or from client.py) for app code. server.py runs as a stdio subprocess.
"""

from utils.mcp.wikidata.client import (
    analyze_reliability,
    get_org_classification,
    get_wikidata_session,
    search_entity,
)

__all__ = [
    "get_wikidata_session",
    "search_entity",
    "get_org_classification",
    "analyze_reliability",
]