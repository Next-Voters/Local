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


class LegislationFinderState(BaseAgentState):
    """Agent-specific state for the legislation finder agent."""

    city: NotRequired[str]
    # Items are plain URL strings for HTML pages or dicts with pre-fetched
    # PDF content: {"url": str, "content": str, "source": "pdf"}.
    legislation_sources: NotRequired[Annotated[list[str | dict], operator.add]]


class ChainData(TypedDict):
    """Data sent through the chain of AI components."""

    city: NotRequired[str]
    topic: NotRequired[str]
    legislation_sources: NotRequired[list[str | dict]]
    legislation_content: NotRequired[list[str]]
    notes: NotRequired[str]
    legislation_summary: NotRequired[WriterOutput]
    markdown_report: NotRequired[str]
