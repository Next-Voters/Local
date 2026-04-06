"""MCP client utilities for connecting to external services.

Primary interface: ``utils.mcp.registry`` — import as ``from utils.mcp import registry as mcp``.

Internal modules:
  - registry.py: Declarative server registry (session management, tool dispatch)
  - session.py: MCPSessionManager (ContextVar-based session reuse)
  - _shared.py: parse_mcp_result helper
  - tavily/server.py: FastMCP server (runs as subprocess, not imported directly)
  - tavily/extract.py: Tavily SDK content extraction (direct API call, not MCP)
"""

from utils.mcp import registry  # noqa: F401 — ensure registrations run at import time

__all__ = ["registry"]
