"""Lead researcher — supervisor agent that orchestrates researchers and validators.

The lead researcher:
1. Identifies specific issues within a topic to investigate
2. Calls researcher_agent_tool for each issue (isolated context per call)
3. Deduplicates collected URLs
4. Calls source_validator_tool on all candidates
5. Produces a final synthesis as LeadResearcherOutput (enforced by response_format)
"""

from __future__ import annotations

import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from config.constants import AGENT_RECURSION_LIMIT, MAX_RESEARCHER_INVOCATIONS
from config.system_prompts import lead_researcher_sys_prompt
from tools.researcher_agent_tool import researcher_agent_tool
from tools.source_validator import source_validator_tool
from utils.llm import get_llm
from utils.schemas import LeadResearcherOutput, LeadResearcherState

logger = logging.getLogger(__name__)


def build_lead_researcher_agent(prompt: str):
    """Build the lead researcher supervisor agent.

    Args:
        prompt: Pre-formatted system prompt (city/topic already resolved).

    Returns:
        A compiled LangGraph agent graph.
    """
    return create_agent(
        model=get_llm(),
        tools=[researcher_agent_tool, source_validator_tool],
        system_prompt=prompt,
        state_schema=LeadResearcherState,
        response_format=LeadResearcherOutput,
        name="lead_researcher",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def invoke_legislation_finder(city: str, topic: str = "") -> dict:
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
