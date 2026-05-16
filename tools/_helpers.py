"""Shared helpers for tool adapters.

Eliminates repeated Command + ToolMessage wrapping boilerplate.
"""

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command


def ok(tool_call_id: str, msg: str = "", **state_updates: Any) -> Command:
    """Build a successful Command with a ToolMessage and optional state updates.

    Args:
        tool_call_id: LangGraph injected tool call ID.
        msg: Human-readable message for the agent's conversation history.
        **state_updates: Additional state fields to include in the update dict.

    Returns:
        A LangGraph Command with messages + any state updates merged in.
    """
    update: dict[str, Any] = {**state_updates}
    update["messages"] = [ToolMessage(content=msg, tool_call_id=tool_call_id)]
    return Command(update=update)


def err(tool_call_id: str, msg: str) -> Command:
    """Build an error Command with a ToolMessage (no state mutations).

    Args:
        tool_call_id: LangGraph injected tool call ID.
        msg: Error message for the agent's conversation history.

    Returns:
        A LangGraph Command with only the error message.
    """
    return Command(
        update={
            "messages": [ToolMessage(content=msg, tool_call_id=tool_call_id)],
        }
    )
