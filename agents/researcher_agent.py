"""Researcher subagent — ReAct discovery loop for a single issue.

Each researcher is scoped to one specific issue within a topic for a city
(e.g., "rent control vote" within "housing" for "Toronto"). It uses web
search, reflection, and note-taking tools to investigate, then produces a
structured ``ResearcherOutput`` as its final response.

Built with ``create_agent`` from langchain; reflection history is injected
via ``ReflectionMiddleware``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from langchain.agents import create_agent

from config.constants import AGENT_RECURSION_LIMIT
from config.system_prompts import legislation_finder_sys_prompt
from tools import web_search, reflection_tool, note_taker, delete_note
from tools.middleware import ReflectionMiddleware
from utils.llm import get_llm
from utils.schemas import ResearcherOutput

logger = logging.getLogger(__name__)

_TARGET_GCAL_TOOLS = {"create_event", "get_calendar_events", "update_event"}


# ---------------------------------------------------------------------------
# Dynamic system prompt
# ---------------------------------------------------------------------------


def _researcher_system_prompt(state: dict) -> str:
    """Format the researcher system prompt with runtime city/topic/issue/dates."""
    return legislation_finder_sys_prompt.format(
        input_city=state.get("region", "Unknown"),
        topic=state.get("topic", ""),
        issue=state.get("issue", ""),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
        today=datetime.today().strftime("%B %d, %Y"),
    )


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------


def build_researcher_agent(gcal_tools: list):
    """Build the researcher agent scoped to one issue within a topic.

    Args:
        gcal_tools: Google Calendar MCP tools (may be empty if MCP failed).

    Returns:
        A compiled LangGraph agent graph.
    """
    selected = [t for t in gcal_tools if t.name in _TARGET_GCAL_TOOLS]
    tools = [reflection_tool, web_search, note_taker, delete_note] + selected

    return create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=_researcher_system_prompt,
        middleware=[ReflectionMiddleware()],
        response_format=ResearcherOutput,
        name="researcher",
    )


# ---------------------------------------------------------------------------
# Runner with graceful recursion-limit exit
# ---------------------------------------------------------------------------


async def run_researcher(graph, invoke_kwargs: dict) -> dict:
    """Run the researcher graph, tolerating recursion-limit exits gracefully.

    Uses ``astream`` with ``stream_mode="values"`` so we see the full state
    at each step. If LangGraph aborts with ``GraphRecursionError`` we still
    return the most recent state snapshot — which contains any URLs the
    agent had already accepted via web_search tool calls.
    """
    from langgraph.errors import GraphRecursionError

    last_state: dict = {}
    try:
        async for state in graph.astream(
            invoke_kwargs["input"],
            config=invoke_kwargs["config"],
            stream_mode="values",
        ):
            last_state = state or last_state
    except GraphRecursionError:
        partial_urls = last_state.get("legislation_sources", []) or []
        logger.warning(
            "Researcher hit recursion limit (%d steps); returning %d partial URLs.",
            invoke_kwargs["config"].get("recursion_limit", AGENT_RECURSION_LIMIT),
            len(partial_urls),
        )
    return last_state
