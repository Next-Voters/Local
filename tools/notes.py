"""Note-taking tools for the researcher agent's scratchpad.

Notes are stored as SystemMessage objects in the messages list, each with a
slug-based ID. Deletion uses LangGraph's RemoveMessage to genuinely remove
the note from the agent's context window.

Why SystemMessage (not ToolMessage): OpenAI requires every tool_call in an
AIMessage to have a matching ToolMessage. If we gave the note's slug ID to
the ToolMessage and later removed it via RemoveMessage, the orphaned
tool_call would cause an API error. Instead, each tool call produces a
normal ToolMessage (auto-ID, stays in history) PLUS a separate SystemMessage
(slug ID, removable).
"""

from typing import Annotated

from langchain_core.messages import RemoveMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command


@tool
def note_taker(
    slug: str,
    note: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Record a research note with a descriptive slug ID.

    Args:
        slug: Short kebab-case identifier (e.g. 'rent-control-vote', 'zoning-reform-update').
        note: The note content — what you found, from which source, and why it matters.
    """
    return Command(update={
        "messages": [
            ToolMessage(content=f"Note '{slug}' recorded.", tool_call_id=tool_call_id),
            SystemMessage(content=f"[RESEARCH_NOTE:{slug}] {note}", id=slug),
        ],
    })


@tool
def delete_note(
    slug: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delete a research note by its slug ID, freeing context window space.

    Use after reflection when a note is superseded, incorrect, or no longer relevant.

    Args:
        slug: The slug ID of the note to delete.
    """
    return Command(update={
        "messages": [
            ToolMessage(content=f"Note '{slug}' deleted from context.", tool_call_id=tool_call_id),
            RemoveMessage(id=slug),
        ],
    })
