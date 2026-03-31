"""Shared utilities for MCP clients."""

import json
from typing import Any


def parse_mcp_result(result: Any) -> dict[str, Any]:
    """Safely parse MCP tool result.

    Args:
        result: Raw result from MCP session.call_tool()

    Returns:
        Parsed dict or error dict
    """
    text_content = ""
    try:
        if hasattr(result, "content") and result.content:
            first_content = result.content[0]
            if hasattr(first_content, "text"):
                text_content = first_content.text
            else:
                return {"error": "Unexpected content type", "raw": str(result)}
        elif hasattr(result, "text"):
            text_content = result.text
        else:
            text_content = str(result) if result else "{}"

        return json.loads(text_content)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw": text_content}
    except Exception as e:
        return {"error": f"Failed to parse result: {e}", "raw": str(result)}
