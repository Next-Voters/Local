"""This includes all typed dictionaries used by the product within multiple applications such as the states for Langgraph"""

from typing import NotRequired, Annotated, TypedDict

import operator

from langchain_core.messages import BaseMessage
from utils.models import ReflectionEntry, WriterOutput


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


class ChainData(TypedDict):
    city: NotRequired[str]
    legislation_sources: NotRequired[str]
    legislation_content: NotRequired[list[LegislationContent]]
    final_output: NotRequired[WriterOutput]
