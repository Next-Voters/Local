"""Reflection tool adapter shared by all ReAct agents.

Generates structured reflections on conversation history to guide
the agent's next action. Uses a lightweight LLM call.
"""

import json
from functools import lru_cache
from typing import Annotated

from langchain_core.messages import BaseMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.schemas import ReflectionEntry
from utils.llm import get_mini_llm
from utils.tools._helpers import ok
from config.system_prompts import reflection_prompt


@lru_cache(maxsize=1)
def _get_mini_model():
    """Lazy-load and cache the mini LLM for reflection calls."""
    return get_mini_llm()


@tool
def reflection_tool(
    tool_call_id: Annotated[str, InjectedToolCallId],
    messages: Annotated[list[BaseMessage], InjectedState("messages")],
) -> Command:
    """Reflects on conversation history to determine the next action."""

    recent_messages = messages[-10:] if len(messages) > 10 else messages
    conversation_summary = "\n".join(
        f"{msg.type}: {msg.content[:500]}" for msg in recent_messages if msg.content
    )

    formatted_prompt = reflection_prompt.format(
        conversation_summary=conversation_summary,
    )
    response = _get_mini_model().invoke(
        [
            {"role": "system", "content": formatted_prompt},
            {
                "role": "user",
                "content": "Produce a structured reflection based on the past conversation",
            },
        ]
    )

    try:
        reflection_data = json.loads(response.content)
        entry = ReflectionEntry(
            reflection=reflection_data.get(
                "reflection", "Unable to produce reflection."
            ),
            gaps_identified=reflection_data.get("gaps_identified", []),
            next_action=reflection_data.get("next_action", "Continue searching."),
        )
    except (json.JSONDecodeError, TypeError):
        entry = ReflectionEntry(
            reflection=response.content[:500],
            gaps_identified=[],
            next_action="Continue searching with more specific queries.",
        )

    return ok(tool_call_id, entry.next_action, reflection_list=[entry])
