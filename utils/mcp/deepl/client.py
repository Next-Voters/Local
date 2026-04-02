"""DeepL MCP client — the interface app code imports.

Launches server.py as a stdio subprocess and exposes an async function for
text translation. Do not run this file directly; import its functions from
your application.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from utils.mcp.session import MCPSessionManager

_SERVER_PATH = str(Path(__file__).parent / "server.py")


def get_api_key() -> str:
    """Get DeepL API key from environment."""
    api_key = os.getenv("DEEPL_API_KEY")
    if not api_key:
        raise ValueError(
            "DEEPL_API_KEY not set in environment. "
            "Get your free key at https://www.deepl.com/pro-api"
        )
    return api_key


@asynccontextmanager
async def get_deepl_session():
    """Get MCP session connected to the local DeepL server via stdio.

    Launches server.py as a subprocess and communicates via stdin/stdout.
    Session is properly cleaned up on exit.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_SERVER_PATH],
        env={**os.environ, "DEEPL_API_KEY": get_api_key()},
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


_manager = MCPSessionManager("deepl_session", get_deepl_session)
managed_deepl_session = _manager.managed_session


async def translate_text(text: str, target_lang: str) -> dict[str, Any]:
    """Translate text to a target language via the DeepL MCP server.

    Args:
        text: The text to translate.
        target_lang: Target language code — "ES" or "FR".

    Returns:
        Dict with translated_text and detected_source_lang, or error dict.
    """
    return await _manager.call_tool(
        "translate_text", {"text": text, "target_lang": target_lang}
    )
