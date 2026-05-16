"""Agent-as-tool wrapper for the researcher subagent.

Gives each researcher invocation its own isolated context window. Called by
the lead researcher for each specific issue it identifies within a topic.
Includes a hard runtime limit on total invocations per lead researcher
execution, enforced via InjectedState counter.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agents.researcher_agent import build_researcher_agent, run_researcher
from config.constants import AGENT_RECURSION_LIMIT, MAX_RESEARCHER_INVOCATIONS
from tools._helpers import ok
from utils.schemas import ResearcherOutput

logger = logging.getLogger(__name__)

_GCAL_MCP_URL = "https://gcal.mintmcp.com/mcp"


# ---------------------------------------------------------------------------
# MCP helper
# ---------------------------------------------------------------------------


async def _load_gcal_tools() -> list:
    """Load Google Calendar MCP tools, falling back to empty on failure."""
    headers: dict[str, str] = {}
    api_key = os.getenv("GLAMA_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        async with streamablehttp_client(_GCAL_MCP_URL, headers=headers) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await load_mcp_tools(session)
    except Exception as exc:
        logger.warning(
            "MCP connection failed (%s); running without calendar tools", exc
        )
        return []


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
async def researcher_agent_tool(
    city: str,
    topic: str,
    issue: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Invoke the researcher subagent to discover legislation for a specific issue.

    Each researcher focuses on one issue (e.g., 'rent control vote') within
    one topic (e.g., 'housing') for a given city. Runs a full ReAct discovery
    loop in an isolated context window.

    Args:
        city: The municipality to research.
        topic: The overarching topic (e.g., 'housing', 'transportation').
        issue: The specific issue to investigate within the topic.
    """
    # --- HARD RUNTIME LIMIT ---
    current_count = state.get("researcher_invocation_count", 0)
    if current_count >= MAX_RESEARCHER_INVOCATIONS:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"LIMIT REACHED: Cannot invoke researcher — "
                            f"{current_count}/{MAX_RESEARCHER_INVOCATIONS} "
                            f"invocations used. Proceed to source validation "
                            f"and synthesis with findings so far."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    # --- Normal execution ---
    gcal_tools = await _load_gcal_tools()
    graph = build_researcher_agent(gcal_tools)

    invoke_kwargs = {
        "input": {
            "region": city,
            "topic": topic,
            "issue": issue,
            "messages": [
                HumanMessage(
                    content=(
                        f"Research this specific issue for {city} ({topic}): {issue}"
                    )
                )
            ],
        },
        "config": {"recursion_limit": AGENT_RECURSION_LIMIT},
    }
    discovery_state = await run_researcher(graph, invoke_kwargs)

    # Extract structured output (enforced by response_format=ResearcherOutput)
    structured: ResearcherOutput | None = discovery_state.get("structured_response")
    if structured:
        summary = structured.research_summary
        sources = structured.legislation_sources
    else:
        # Fallback for recursion-limit exits (partial state, no structured response)
        summary = "Researcher hit recursion limit; partial results returned."
        sources = discovery_state.get("legislation_sources", [])

    return Command(
        update={
            "messages": [
                ToolMessage(content=summary, tool_call_id=tool_call_id)
            ],
            "legislation_sources": sources,
            "researcher_invocation_count": 1,  # adds 1 via operator.add reducer
        }
    )
