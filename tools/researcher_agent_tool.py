"""Agent-as-tool wrapper for the researcher subagent.

Gives each researcher invocation its own isolated context window. Called by
the lead researcher for each specific issue it identifies within a topic.
Includes a hard runtime limit on total invocations per lead researcher
execution, enforced via InjectedState counter.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from agents.researcher_agent import build_researcher_agent
from config.constants import AGENT_RECURSION_LIMIT, MAX_RESEARCHER_INVOCATIONS


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
async def researcher_agent_tool(
    city: str,
    topic: str,
    issue: str,
    search_guidance: str,
    topic_description: str,
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
        search_guidance: City-specific search strategy (governing body name,
            official domains, portal URLs, terminology) for the researcher
            to use when crafting web search queries.
        topic_description: Definition of the topic (e.g., 'Federal, state,
            and local immigration policy') so the researcher can filter
            for topic relevance.
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

    agent = build_researcher_agent({
        "region": city,
        "topic": topic,
        "issue": issue,
        "search_guidance": search_guidance,
        "topic_description": topic_description,
    })

    agent_response = await agent.ainvoke(
        input={
            "region": city,
            "messages": [
                HumanMessage(
                    content=(
                        f"Research this specific issue for {city} ({topic}): {issue}"
                    )
                )
            ],
        },
        config={"recursion_limit": AGENT_RECURSION_LIMIT},
    )

    # Extract from state written by handoff tool
    summary = agent_response.get("research_summary")
    sources = agent_response.get("legislation_sources", [])

    if not summary:
        summary = "Researcher returned no summary for this issue."

    return Command(
        update={
            "messages": [
                ToolMessage(content=summary, tool_call_id=tool_call_id)
            ],
            "legislation_sources": sources,
            "researcher_invocation_count": 1,
        }
    )
