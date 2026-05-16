"""Lead researcher — supervisor agent that orchestrates researchers.

The lead researcher:
1. Identifies specific issues within a topic to investigate
2. Calls researcher_agent_tool for each issue (isolated context per call)
3. Produces a render-ready publication state as LeadResearcherOutput (enforced by response_format)
"""

from __future__ import annotations

from langchain.agents import create_agent

from tools.researcher_agent_tool import researcher_agent_tool
from utils.llm import get_llm
from utils.schemas import LeadResearcherOutput, LeadResearcherState


def build_lead_researcher_agent(prompt: str):
    """Build the lead researcher supervisor agent.

    Args:
        prompt: Pre-formatted system prompt (city/topic already resolved).

    Returns:
        A compiled LangGraph agent graph.
    """
    return create_agent(
        model=get_llm(),
        tools=[researcher_agent_tool],
        system_prompt=prompt,
        state_schema=LeadResearcherState,
        response_format=LeadResearcherOutput,
        name="lead_researcher",
    )
