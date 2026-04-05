"""Tool adapters for external data services.

Each tool is a thin adapter that calls an MCP server and wraps results
in LangGraph Commands for state updates.
"""

from utils.tools.web_search import web_search

__all__: list[str] = ["web_search"]
