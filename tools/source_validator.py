"""Source validation tool for the lead researcher.

Validates candidate legislation URLs in parallel using structured LLM calls.
Each URL is independently classified by a stateless mini-LLM validator.

Ported from agents/legislation_finder.py (_run_per_source_subagent +
_dispatch_subagents) with no logic changes.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command

from config.system_prompts import legislation_finder_subagent_sys_prompt
from tools._helpers import ok
from utils.llm import get_structured_mini_llm
from utils.schemas import SourceAssessment
from utils.sources import extract_url_and_snippet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-source validator (stateless, bounded)
# ---------------------------------------------------------------------------


def _run_per_source_subagent(
    city: str, item: str | dict[str, Any]
) -> SourceAssessment:
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
            assessment = SourceAssessment(url=url, accepted=False)
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
        return list(
            executor.map(
                lambda item: _run_per_source_subagent(city, item), candidates
            )
        )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
def source_validator_tool(
    city: str,
    candidates: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Validate candidate legislation URLs in parallel.

    Classifies each URL and decides whether it meets the research quality bar.
    Returns accepted URLs and per-source assessments.

    Args:
        city: The municipality the URLs are about.
        candidates: List of candidate URLs to validate.
    """
    assessments = _dispatch_subagents(city, candidates)
    accepted = [a.url for a in assessments if a.accepted]
    summary = (
        f"Validated {len(candidates)} URLs: {len(accepted)} accepted, "
        f"{len(candidates) - len(accepted)} rejected."
    )
    return ok(
        tool_call_id,
        summary,
        legislation_sources=accepted,
        source_assessments=[a.model_dump() for a in assessments],
    )
