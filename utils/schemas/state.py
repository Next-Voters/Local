"""Typed dictionaries for LangGraph agent states."""

from typing import NotRequired, Annotated, TypedDict

import operator

from langchain_core.messages import BaseMessage
from utils.schemas.pydantic import ReflectionEntry, WriterOutput


class BaseAgentState(TypedDict):
    """Shared state fields that every ReAct agent inherits.

    Agent-specific states extend this with their own fields.
    """

    messages: Annotated[list[BaseMessage], operator.add]
    reflection_list: NotRequired[Annotated[list[ReflectionEntry], operator.add]]


class ReliableLegislationSources(TypedDict):
    url: str
    organization: str


class LegislationFinderState(BaseAgentState):
    """Agent-specific state for the legislation finder agent."""

    city: NotRequired[str]
    raw_legislation_sources: NotRequired[
        Annotated[list[ReliableLegislationSources], operator.add]
    ]
    reliable_legislation_sources: NotRequired[Annotated[list[str], operator.add]]


class LegislationContent(TypedDict):
    source: str
    content: str
    error: NotRequired[str]


class IndividualStatementSummary(TypedDict):
    """The information about a statement made by a politician for a specific legislative source."""

    source: str
    summary: str


class PoliticianStatementSummary(TypedDict):
    """The information about a politician that is dealing with legislation explored."""

    name: str
    statement_summaries: list[IndividualStatementSummary]


class ChainData(TypedDict):
    """Data sent through the chain of AI components."""

    city: NotRequired[str]
    legislation_sources: NotRequired[str]
    legislation_content: NotRequired[list[LegislationContent]]
    notes: NotRequired[str]
    politician_public_statements: NotRequired[list[PoliticianStatementSummary]]
    legislation_summary: NotRequired[WriterOutput]
    markdown_report: NotRequired[str]


class PoliticalFigure(TypedDict):
    """A political figure found by the political_figure_finder tool."""

    name: str
    position: str
    party: NotRequired[str]
    jurisdiction: str
    source_url: NotRequired[str]


class PoliticalCommentaryState(BaseAgentState):
    """Agent-specific state for the political commentary agent."""

    city: NotRequired[str]
    country: NotRequired[str]
    political_figures: NotRequired[Annotated[list[PoliticalFigure], operator.add]]
    current_political_figure: NotRequired[str]
    blog_urls: NotRequired[Annotated[list[str], operator.add]]
