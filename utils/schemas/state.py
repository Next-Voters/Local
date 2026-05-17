"""Typed dictionaries for LangGraph agent states."""

from typing import NotRequired, Annotated, TypedDict

import operator

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from utils.schemas.pydantic import (
    ReflectionEntry,
    SourceAssessment,
    WriterOutput,
)


class BaseAgentState(TypedDict):
    """Shared state fields that every ReAct agent inherits.

    Uses ``add_messages`` reducer (not ``operator.add``) to support
    LangGraph's ``RemoveMessage`` pattern needed by delete_note.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    reflection_list: NotRequired[Annotated[list[ReflectionEntry], operator.add]]


class ResearcherState(BaseAgentState):
    """State for the researcher subagent. Scoped to one issue within a topic.

    Notes are NOT a state field — they live in ``messages`` as SystemMessage
    objects with slug-based IDs. delete_note uses RemoveMessage to remove them.
    """

    region: NotRequired[str]
    topic: NotRequired[str]
    issue: NotRequired[str]
    search_guidance: NotRequired[str]
    legislation_sources: NotRequired[Annotated[list[str | dict], operator.add]]
    research_summary: NotRequired[str]


class LeadResearcherState(TypedDict):
    """State for the lead researcher supervisor. Operates on one region + one topic.

    Does not extend BaseAgentState — the supervisor delegates and synthesizes,
    it does not reflect.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    region: NotRequired[str]
    topic: NotRequired[str]
    legislation_sources: NotRequired[Annotated[list[str | dict], operator.add]]
    researcher_invocation_count: NotRequired[Annotated[int, operator.add]]


# Legacy state — kept for downstream pipeline nodes (content_retrieval,
# note_taker, summary_writer) which are not being changed in this refactor.
class LegislationFinderState(BaseAgentState):
    """Agent-specific state for the legislation finder agent (legacy)."""

    region: NotRequired[str]
    legislation_sources: NotRequired[Annotated[list[str | dict], operator.add]]
    source_assessments: NotRequired[list[SourceAssessment]]


class TopicResult(TypedDict):
    """Per-topic pipeline results accumulated across nodes."""

    legislation_sources: NotRequired[list[str | dict]]
    legislation_content: NotRequired[list[str]]
    notes: NotRequired[str]
    legislation_summary: NotRequired[WriterOutput]
    findings: NotRequired[list[dict]]
    overview: NotRequired[str]


class ChainData(TypedDict):
    """Data sent through the chain of AI components.

    The pipeline processes all topics for a region in a single invocation.
    Topics are fetched from Supabase in the legislation_finder node.
    Per-topic intermediate state lives in ``topic_results``.
    """

    region: NotRequired[str]
    topic_results: NotRequired[dict[str, TopicResult]]
