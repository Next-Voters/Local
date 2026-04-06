"""Centralized MCP server registry.

Replaces per-service client.py files with a single declarative registry.
Servers are registered at module level; session managers are created lazily
on first use. The underlying MCPSessionManager + ContextVar pattern from
session.py is preserved for async safety.

Usage:
    from utils.mcp import registry as mcp

    # Pre-initialize subprocess for an agent invocation (session reuse):
    async with mcp.session("tavily"):
        result = await mcp.call("tavily", "search_legislation", {...})

    # One-shot call (opens + closes subprocess automatically):
    result = await mcp.call("tavily", "search_legislation", {...})

    # Check if a server's credentials are available:
    if mcp.is_configured("google_calendar"):
        ...
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from utils.mcp.session import MCPSessionManager

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Module-level registries — populated at import time, read-only thereafter.
_specs: dict[str, "_ServerSpec"] = {}
_managers: dict[str, MCPSessionManager] = {}


@dataclass(frozen=True)
class _ServerSpec:
    """Immutable specification for a registered MCP server."""

    command: str
    args: list[str]
    env: Callable[[], dict[str, str]]
    configured: Callable[[], bool] = field(default=lambda: True)


def register(
    name: str,
    *,
    command: str,
    args: list[str],
    env: Callable[[], dict[str, str]],
    configured: Callable[[], bool] = lambda: True,
) -> None:
    """Declare an MCP server by name.

    Called at module level before any async code. The env callable is invoked
    lazily at session-open time so environment variables are read on demand.

    Args:
        name: Unique identifier for the server (e.g. "tavily", "google_calendar").
        command: Executable to run (e.g. sys.executable or "npx").
        args: Command arguments (e.g. ["path/to/server.py"] or ["-y", "pkg"]).
        env: Callable returning extra env vars to merge into the subprocess env.
        configured: Callable returning True if the server's prerequisites are met.
    """
    _specs[name] = _ServerSpec(
        command=command,
        args=list(args),
        env=env,
        configured=configured,
    )


def _get_manager(name: str) -> MCPSessionManager:
    """Lazily create (and cache) an MCPSessionManager for the named server."""
    if name not in _managers:
        spec = _specs.get(name)
        if spec is None:
            raise KeyError(f"MCP server '{name}' is not registered")

        @asynccontextmanager
        async def _factory():
            resolved_env = spec.env()
            params = StdioServerParameters(
                command=spec.command,
                args=spec.args,
                env={**os.environ, **resolved_env},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as sess:
                    await sess.initialize()
                    yield sess

        _managers[name] = MCPSessionManager(f"{name}_session", _factory)
    return _managers[name]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Invoke an MCP tool on the named server.

    Reuses the active session if one was opened via session(), otherwise
    opens a temporary subprocess for this single call.

    Args:
        server: Registered server name (e.g. "tavily").
        tool: MCP tool name as defined on the server (e.g. "search_legislation").
        args: Tool arguments dict.

    Returns:
        Parsed response dict from the MCP server.
    """
    return await _get_manager(server).call_tool(tool, args)


def session(server: str):
    """Context manager that pre-initializes a subprocess for session reuse.

    Use this in pipeline nodes before invoking an agent so all tool calls
    within that agent invocation share a single subprocess.

    Args:
        server: Registered server name (e.g. "tavily").

    Example:
        async with mcp.session("tavily"):
            await agent.ainvoke(...)
    """
    return _get_manager(server).managed_session()


def is_configured(server: str) -> bool:
    """Check whether a server's credentials/prerequisites are available.

    Args:
        server: Registered server name.

    Returns:
        True if the server is registered and its configured() check passes.
    """
    spec = _specs.get(server)
    if spec is None:
        return False
    return spec.configured()


# ---------------------------------------------------------------------------
# Server registrations
# ---------------------------------------------------------------------------

_TAVILY_SERVER_PATH = str(_PROJECT_ROOT / "utils" / "mcp" / "tavily" / "server.py")


def _tavily_api_key() -> str:
    """Read Tavily API key from environment; raise ValueError if missing."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY not set in environment. "
            "Get your key at https://app.tavily.com/"
        )
    return api_key


register(
    "tavily",
    command=sys.executable,
    args=[_TAVILY_SERVER_PATH],
    env=lambda: {"TAVILY_API_KEY": _tavily_api_key()},
)

register(
    "google_calendar",
    command="npx",
    args=["-y", "@cocal/google-calendar-mcp"],
    env=lambda: {
        "GOOGLE_OAUTH_CREDENTIALS": os.getenv("GOOGLE_OAUTH_CREDENTIALS", ""),
    },
    configured=lambda: bool(
        os.getenv("GOOGLE_OAUTH_CREDENTIALS", "")
        and os.path.exists(os.getenv("GOOGLE_OAUTH_CREDENTIALS", ""))
    ),
)
