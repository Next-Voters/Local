"""Shared MCP session management utilities."""

from contextlib import asynccontextmanager, AsyncExitStack
from contextvars import ContextVar
from typing import Any, Callable, AsyncContextManager

from mcp import ClientSession

from utils.mcp._shared import parse_mcp_result


class MCPSessionManager:
    """Reusable MCP subprocess session manager via ContextVar injection.

    Wraps a raw session factory and exposes:
    - managed_session(): context manager that pre-initializes one subprocess
      and stores it in a ContextVar so all tool calls within the same async
      context reuse it instead of spawning new processes.
    - call_tool(): invokes an MCP tool, reusing the active session if one
      is set, or opening a temporary session otherwise.
    """

    def __init__(
        self,
        name: str,
        session_factory: Callable[[], AsyncContextManager[ClientSession]],
    ) -> None:
        self._active: ContextVar[ClientSession | None] = ContextVar(name, default=None)
        self._factory = session_factory

    @asynccontextmanager
    async def managed_session(self):
        """Pre-initialize one subprocess to be reused by all tool calls in this context."""
        async with AsyncExitStack() as stack:
            session = await stack.enter_async_context(self._factory())
            token = self._active.set(session)
            stack.callback(self._active.reset, token)
            yield session

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool, reusing any active session or opening a temporary one."""
        session = self._active.get()
        if session is not None:
            return parse_mcp_result(await session.call_tool(tool_name, args))
        async with self._factory() as new_session:
            return parse_mcp_result(await new_session.call_tool(tool_name, args))