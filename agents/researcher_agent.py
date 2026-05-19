"""Researcher subagent — ReAct discovery loop for a single issue.

Each researcher is scoped to one specific issue within a topic for a city
(e.g., "rent control vote" within "housing" for "Toronto"). It uses web
search, reflection, and note-taking tools to investigate, then terminates
via the ``handoff`` tool which writes findings directly to graph state.

Built with ``create_agent`` from langchain; reflection history is injected
via ``ReflectionMiddleware``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from langchain.agents import create_agent

from config.system_prompts import legislation_finder_sys_prompt, legislation_finder_task_sys_prompt
from tools import web_search, reflection_tool, note_taker, delete_note
from tools.middleware import ReflectionMiddleware
from tools.handoff import handoff
from utils.llm import get_llm
from utils.schemas import ResearcherOutput, ResearcherState

def _researcher_system_prompt(state: dict) -> str:
    """Format the researcher system prompt with runtime city/topic/issue/dates.

    When search_guidance is present (passed from the lead researcher via
    city_details_tool), uses the targeted task prompt that replaces generic
    Step 2 boilerplate with city-specific search strategy. Otherwise falls
    back to the original generic prompt.
    """
    base_kwargs = dict(
        input_city=state.get("region", "Unknown"),
        topic=state.get("topic", ""),
        topic_description=state.get("topic_description", ""),
        issue=state.get("issue", ""),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
        today=datetime.today().strftime("%B %d, %Y"),
    )
    if state.get("search_guidance"):
        return legislation_finder_task_sys_prompt.format(
            **base_kwargs, search_guidance=state["search_guidance"],
        )
    return legislation_finder_sys_prompt.format(**base_kwargs)


def build_researcher_agent(state: dict):
    """Build the researcher agent scoped to one issue within a topic.

    Args:
        state: Runtime state dict with region, topic, issue, and
            optionally search_guidance — used to format the system prompt.

    Returns:
        A compiled LangGraph agent graph.
    """
    tools = [reflection_tool, web_search, note_taker, delete_note, handoff]

    return create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=_researcher_system_prompt(state),
        state_schema=ResearcherState,
        response_format=ResearcherOutput,
        middleware=[ReflectionMiddleware()],
        name="researcher",
    )


