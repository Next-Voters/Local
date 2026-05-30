"""Lead researcher — supervisor agent that orchestrates researchers.

The lead researcher:
1. Identifies specific issues within a topic to investigate
2. Calls researcher_agent_tool for each issue (isolated context per call)
3. Produces a render-ready publication state as LeadResearcherOutput (enforced by response_format)
"""

from __future__ import annotations

from langchain.agents import create_agent

from config.constants import MAX_RESEARCHER_INVOCATIONS
from config.system_prompts import lead_researcher_sys_prompt
from tools.region_details import region_details_tool
from tools.researcher_agent_tool import researcher_agent_tool
from utils.llm import get_llm
from utils.schemas import LeadResearcherOutput, LeadResearcherState

# ---------------------------------------------------------------------------
# Dynamic system prompt
# ---------------------------------------------------------------------------


def _lead_researcher_system_prompt(state: dict) -> str:
    """Format the lead researcher system prompt with runtime city/topic values."""
    base_kwargs = dict(
        city=state.get("region", "Unknown"),
        topic=state.get("topic", ""),
        topic_description=state.get("topic_description", ""),
        max_invocations=MAX_RESEARCHER_INVOCATIONS,
    )
    return lead_researcher_sys_prompt.format(**base_kwargs)


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------


def build_lead_researcher_agent(state: dict):
    """Build the lead researcher supervisor agent.

    Args:
        state: Runtime state dict with region, topic, and
            topic_description — used to format the system prompt.

    Returns:
        A compiled LangGraph agent graph.
    """
    return create_agent(
        model=get_llm(),
        tools=[region_details_tool, researcher_agent_tool],
        system_prompt=_lead_researcher_system_prompt(state),
        state_schema=LeadResearcherState,
        response_format=LeadResearcherOutput,
        name="lead_researcher",
    )
