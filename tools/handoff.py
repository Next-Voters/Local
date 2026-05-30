"""Handoff tool for researcher agent termination.

When the researcher has gathered sufficient findings, it calls this tool
to write its summary and sources to state and exit the graph cleanly.
"""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command


@tool(return_direct=True)  # type: Literal[True] — routes to END via create_agent
def handoff(
    research_summary: str,
    legislation_sources: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[dict]:
    """Complete research and hand off findings to the lead researcher.

    Args:
        research_summary: Concise synthesis of findings for the researched issue.
        legislation_sources: All validated source URLs discovered.
    """
    return Command(
        update={
            "messages": [
                ToolMessage(content="Handoff complete.", tool_call_id=tool_call_id)
            ],
            "research_summary": research_summary,
            "legislation_sources": legislation_sources,
        },
    )
