from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.lead_researcher_agent import build_lead_researcher_agent
from config.constants import AGENT_RECURSION_LIMIT, MAX_RESEARCHER_INVOCATIONS
from config.system_prompts import lead_researcher_sys_prompt
from utils.schemas.research_output import LeadResearcherOutput


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def invoke_lead_researcher_agent(city: str, topic: str = "") -> dict:
    """Run the lead researcher for a city + topic.

    Public entry point consumed by ``pipelines/node/legislation_finder.py``.

    Returns:
        Dict with ``legislation_sources``, ``findings``, ``final_summary``,
        and optionally ``source_assessments``.
    """
    prompt = lead_researcher_sys_prompt.format(
        city=city,
        topic=topic,
        max_invocations=MAX_RESEARCHER_INVOCATIONS,
    )
    agent = build_lead_researcher_agent(prompt)

    result = await agent.ainvoke(
        {
            "region": city,
            "topic": topic,
            "messages": [
                HumanMessage(
                    content=(
                        f"Research {topic} legislation for {city}. "
                        f"Identify specific issues within this topic, dispatch "
                        f"researchers for each, then validate and synthesize findings."
                    )
                )
            ],
        },
        config={"recursion_limit": AGENT_RECURSION_LIMIT},
    )

    # Extract validated structured output
    structured: LeadResearcherOutput | None = result.get("structured_response")
    if structured:
        return {
            "legislation_sources": structured.legislation_sources,
            "findings": [f.model_dump() for f in structured.findings],
            "final_summary": structured.final_summary,
        }

    # Fallback for edge cases (recursion limit, unexpected termination)
    return {
        "legislation_sources": result.get("legislation_sources", []),
        "source_assessments": result.get("source_assessments", []),
    }
