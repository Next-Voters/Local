"""Tavily MCP service — search (via MCP server) and content extraction (via SDK).

server.py: FastMCP server registered in utils.mcp.registry (runs as subprocess)
extract.py: Tavily SDK URL content extraction (direct API call, not MCP)
"""

from utils.mcp.tavily.extract import extract_url_content

__all__ = ["extract_url_content"]
