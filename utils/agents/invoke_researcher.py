from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.researcher_agent import build_researcher_agent
from config.constants import AGENT_RECURSION_LIMIT

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def invoke_researcher_agent(
    city: str,
    topic: str,
    issue: str,
    search_guidance: str = "",
    topic_description: str = "",
) -> dict:
    """Run a researcher subagent for a single issue within a topic.

    Public entry point consumed by ``tools/researcher_agent_tool.py``.
    Each invocation gets its own isolated context window.

    Returns:
        Dict with ``research_summary`` and ``legislation_sources``.
    """
    state = dict(
        region=city,
        topic=topic,
        issue=issue,
        search_guidance=search_guidance,
        topic_description=topic_description,
    )
    agent = build_researcher_agent(state)

    result = await agent.ainvoke(
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
    summary = result.get("research_summary")
    sources = result.get("legislation_sources", [])

    if not summary:
        summary = "Researcher returned no summary for this issue."

    return {
        "research_summary": summary,
        "legislation_sources": sources,
    }
