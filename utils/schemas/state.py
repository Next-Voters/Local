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


class ChainData(TypedDict):
    """Data sent through the chain of AI components."""

    city: NotRequired[str]
    legislation_sources: NotRequired[str]
    notes: NotRequired[str]
    legislation_summary: NotRequired[WriterOutput]
    markdown_report: NotRequired[str]


class PoliticalFigure(TypedDict):
    """A political figure found by the political_figure_finder tool."""

    name: str
    position: str
    party: NotRequired[str]
    jurisdiction: str
    source_url: NotRequired[str]


class PoliticalCommentary(TypedDict):
    """Unified political commentary with politician name, source URL, and extracted comment."""

    politician: str
    source_url: str
    comment: str


class SocialMediaPost(TypedDict):
    """A social media post from a politician's official account."""

    politician: str
    platform: str
    tweet_id: NotRequired[str]
    text: str
    created_at: NotRequired[str]
    engagement: NotRequired[dict]


class PoliticalCommentaryState(BaseAgentState):
    """Agent-specific state for the political commentary agent."""

    city: NotRequired[str]
    country: NotRequired[str]
    political_figures: NotRequired[Annotated[list[PoliticalFigure], operator.add]]
    political_commentary: NotRequired[
        Annotated[list[PoliticalCommentary], operator.add]
    ]
    research_notes: NotRequired[str]
    social_media_posts: NotRequired[Annotated[list[SocialMediaPost], operator.add]]
