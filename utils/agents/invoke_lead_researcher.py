from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.lead_researcher_agent import build_lead_researcher_agent
from config.constants import AGENT_RECURSION_LIMIT
from utils.schemas.research_output import LeadResearcherOutput

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def invoke_lead_researcher_agent(
    city: str,
    topic: str = "",
    topic_description: str = "",
) -> dict:
    """Run the lead researcher for a city + topic.

    Public entry point consumed by ``pipelines/node/run_agent_team.py``.

    Returns:
        Dict with ``legislation_sources``, ``findings``, and ``overview``.
    """
    state = dict(
        region=city,
        topic=topic,
        topic_description=topic_description,
    )
    agent = build_lead_researcher_agent(state)

    result = await agent.ainvoke(
        {
            "region": city,
            "topic": topic,
            "messages": [
                HumanMessage(
                    content=(
                        f"Research {topic} legislation for {city}. "
                        f"Identify specific issues within this topic, dispatch "
                        f"researchers for each, then synthesize findings."
                    )
                )
            ],
        },
        config={"recursion_limit": AGENT_RECURSION_LIMIT},
    )

    # Extract validated structured output, enriching curated URLs with
    # content dicts accumulated in state from web_search calls.
    structured: LeadResearcherOutput | None = result.get("structured_response")
    if structured:
        accumulated = result.get("legislation_sources", [])
        content_map = {
            item["url"]: item for item in accumulated if isinstance(item, dict)
        }
        enriched = [content_map.get(url, url) for url in structured.legislation_sources]
        return {
            "legislation_sources": enriched,
            "findings": [f.model_dump() for f in structured.findings],
            "overview": structured.overview,
        }

    # Fallback for edge cases (recursion limit, unexpected termination)
    return {
        "legislation_sources": result.get("legislation_sources", []),
        "findings": [],
        "overview": "",
    }
