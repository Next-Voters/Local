"""Legislation finder — supervisor + per-source sub-agent architecture.

Tier A1 — graceful exit:
    The discovery ReAct loop is driven by ``astream`` rather than ``ainvoke``
    so that a ``GraphRecursionError`` returns whatever URLs have already been
    accumulated in state, instead of erasing them.

Tier A2 — supervisor / sub-agent split:
    1. ``_run_discovery_agent`` — the original ReAct agent. Its sole job is
       now to surface *candidate* URLs (via web_search) and optionally create
       calendar events. It is the "discovery" layer of the supervisor.
    2. ``_run_per_source_subagent`` — a bounded, stateless validator that
       classifies one URL at a time and produces a ``SourceAssessment``.
    3. ``invoke_legislation_finder`` is the supervisor: it runs discovery,
       fans out per-source sub-agents through ``ThreadPoolExecutor``, and returns
       both the filtered URL list and the per-source assessments so the
       downstream pipeline can use them without re-running the ReAct loop.

Keeping supervisor and sub-agent colocated per the plan's preference to keep
related agent code in a single file.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agents.base_agent_template import BaseReActAgent
from config.constants import AGENT_RECURSION_LIMIT
from config.system_prompts import (
    legislation_finder_subagent_sys_prompt,
    legislation_finder_sys_prompt,
)
from concurrent.futures import ThreadPoolExecutor

from utils.llm import get_structured_mini_llm
from utils.schemas import LegislationFinderState, SourceAssessment
from utils.sources import extract_url_and_snippet
from utils.tools import web_search

logger = logging.getLogger(__name__)

_GCAL_MCP_URL = "https://gcal.mintmcp.com/mcp"
_TARGET_GCAL_TOOLS = {"create_event", "get_calendar_events", "update_event"}


# ---------------------------------------------------------------------------
# Discovery sub-layer — the original ReAct agent
# ---------------------------------------------------------------------------


def _build_agent(gcal_tools: list) -> object:
    """Build the discovery ReAct agent with web_search + (optional) calendar tools."""
    selected = [t for t in gcal_tools if t.name in _TARGET_GCAL_TOOLS]
    agent = BaseReActAgent(
        state_schema=LegislationFinderState,
        tools=[web_search] + selected,
        system_prompt=lambda state: legislation_finder_sys_prompt.format(
            input_city=state.get("region", "Unknown"),
            last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
            today=datetime.today().strftime("%B %d, %Y"),
        ),
    )
    return agent.build()


async def _run_discovery_agent(graph, invoke_kwargs: dict) -> dict:
    """Run the ReAct graph, tolerating recursion-limit exits gracefully.

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
            "Legislation finder hit recursion limit (%d steps); "
            "returning %d partial URLs.",
            invoke_kwargs["config"].get("recursion_limit", AGENT_RECURSION_LIMIT),
            len(partial_urls),
        )
    return last_state


# ---------------------------------------------------------------------------
# Per-source sub-agent — bounded, stateless validator
# ---------------------------------------------------------------------------


def _run_per_source_subagent(city: str, item: str | dict[str, Any]) -> SourceAssessment:
    """Invoke the structured mini-LLM on one candidate URL.

    Returns a :class:`SourceAssessment`. On LLM failure, falls back to a
    reject decision rather than raising so the supervisor batch keeps going.
    """
    url, snippet = extract_url_and_snippet(item)
    if not url:
        return SourceAssessment(url="", accepted=False)

    llm = get_structured_mini_llm(SourceAssessment)
    user = (
        f"City: {city}\nURL: {url}\n"
        f"Snippet (may be empty):\n{snippet or '(none)'}"
    )
    try:
        result = llm.invoke(
            [
                {"role": "system", "content": legislation_finder_subagent_sys_prompt},
                {"role": "user", "content": user},
            ]
        )
        if isinstance(result, SourceAssessment):
            assessment = result
        elif isinstance(result, dict):
            assessment = SourceAssessment(**result)
        else:
            assessment = SourceAssessment(
                url=url,
                accepted=False,
            )
        if not assessment.url:
            assessment = assessment.model_copy(update={"url": url})
        return assessment
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sub-agent failed for %s: %s", url, exc)
        return SourceAssessment(url=url, accepted=False)


def _dispatch_subagents(
    city: str, candidates: list[str | dict[str, Any]]
) -> list[SourceAssessment]:
    """Fan out per-source validators in parallel and collect assessments."""
    if not candidates:
        return []
    with ThreadPoolExecutor() as executor:
        return list(executor.map(
            lambda item: _run_per_source_subagent(city, item), candidates
        ))


# ---------------------------------------------------------------------------
# Supervisor entry point
# ---------------------------------------------------------------------------


async def invoke_legislation_finder(city: str) -> dict:
    """Supervisor: discover candidate URLs, then validate each in parallel.

    Returns a dict matching the legacy shape (``legislation_sources``,
    ``messages``, …) plus an added ``source_assessments`` list for callers
    that want the per-source metadata.
    """
    from langchain_core.messages import HumanMessage

    invoke_kwargs = {
        "input": {
            "region": city,
            "messages": [
                HumanMessage(content=f"Find recent legislation for {city}.")
            ],
        },
        "config": {"recursion_limit": AGENT_RECURSION_LIMIT},
    }

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
                gcal_tools = await load_mcp_tools(session)
                graph = _build_agent(gcal_tools)
                discovery_state = await _run_discovery_agent(graph, invoke_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP connection failed (%s); running without calendar tools", exc)
        graph = _build_agent([])
        discovery_state = await _run_discovery_agent(graph, invoke_kwargs)

    candidates: list[str | dict[str, Any]] = (
        discovery_state.get("legislation_sources", []) or []
    )

    seen: set[str] = set()
    unique_candidates: list[str | dict[str, Any]] = []
    for c in candidates:
        url, _ = extract_url_and_snippet(c)
        if url and url not in seen:
            seen.add(url)
            unique_candidates.append(c)

    assessments = _dispatch_subagents(city, unique_candidates)
    accepted_urls = {a.url for a in assessments if a.accepted and a.url}

    filtered_sources: list[str | dict[str, Any]] = []
    for c in unique_candidates:
        url, _ = extract_url_and_snippet(c)
        if url in accepted_urls:
            filtered_sources.append(c)

    logger.info(
        "Legislation finder (%s): %d candidates → %d accepted by sub-agents.",
        city,
        len(unique_candidates),
        len(filtered_sources),
    )

    return {
        **discovery_state,
        "legislation_sources": filtered_sources,
        "source_assessments": [a.model_dump() for a in assessments],
    }
