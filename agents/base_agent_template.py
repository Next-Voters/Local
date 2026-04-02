"""Base ReAct agent template for NV Local AI agents.

This module provides the BaseReActAgent class that all NV Local agents inherit from.
It handles reflection handling, tool node setup, and ReAct agent graph construction
using LangGraph.

Key class:
    BaseReActAgent: ReAct-style agent with reflection context management.
                    Supports dynamic system system_prompts, configurable LLM settings,
                    and automatic reflection accumulation in agent state.

The agent builds a LangGraph StateGraph with call_model and tool_node nodes,
implementing the ReAct (Reason + Act) pattern for tool-augmented reasoning.
"""

import json
from functools import lru_cache
from typing import Callable, Union, TypeVar, Type, Annotated

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.schemas import ReflectionEntry, BaseAgentState
from utils.llm import get_llm, get_mini_llm
from config.system_prompts import reflection_prompt

StateType = TypeVar("StateType")

_REFLECTION_PREAMBLE = "Here are previous reflections. Use as context to drive your next actions/decisions:\n\n"


# ---------------------------------------------------------------------------
# Reflection tool (shared by all agents)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_mini_model():
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

    # Parse the structured reflection
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

    return Command(
        update={
            "reflection_list": [entry],
            "messages": [
                ToolMessage(content=entry.next_action, tool_call_id=tool_call_id)
            ],
        }
    )


# ---------------------------------------------------------------------------
# BaseReActAgent
# ---------------------------------------------------------------------------

class BaseReActAgent:
    """Base class for ReAct agents with shared reflection handling.

    Every agent's state must include a `reflection_list` field
    (list[ReflectionEntry]) so the base class can prepend accumulated
    reflections to the system prompt on each model call.

    system_prompt accepts:
      - str: used as-is on every call (most agents)
      - callable(state) -> str: called each invocation for dynamic formatting
    """

    def __init__(
        self,
        state_schema: Type[BaseAgentState],
        tools: list,
        system_prompt: Union[str, Callable[[StateType], str]],
        # Optional LLM config
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        max_tokens: int = 2000,
        timeout: int = 30,
        recursion_limit: int = 25,
    ):
        self.state_schema = state_schema
        # Always include reflection_tool by default
        self.tools = [reflection_tool] + tools
        self.system_prompt = system_prompt
        self.recursion_limit = recursion_limit

        self.model = get_llm(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def _build_prompt(self, state: StateType) -> str:
        """Shared reflection context + agent prompt (static or dynamic)."""
        reflection_list: list[ReflectionEntry] = state.get("reflection_list", [])

        reflection_section = ""
        if reflection_list:
            entries = []
            for r in reflection_list:
                gaps = ", ".join(r.gaps_identified) if r.gaps_identified else "None"
                entries.append(
                    f"- {r.reflection}\n  Gaps: {gaps}\n  Next action: {r.next_action}"
                )
            reflection_section = _REFLECTION_PREAMBLE + "\n".join(entries) + "\n\n"

        agent_prompt = (
            self.system_prompt(state)
            if callable(self.system_prompt)
            else self.system_prompt
        )

        return reflection_section + agent_prompt

    def _should_continue(self, state: StateType) -> bool:
        """Check if the last message has tool calls to process."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return True
        return False

    def _call_model(self, state: StateType) -> dict:
        """Call the LLM with reflection-enriched system prompt + messages."""
        messages = state["messages"]
        system_prompt = self._build_prompt(state)
        model_with_tools = self.model.bind_tools(self.tools)

        response = model_with_tools.invoke(
            [{"role": "system", "content": system_prompt}] + messages
        )

        return {"messages": [response]}

    def build(self):
        """Build and compile the LangGraph ReAct loop."""
        tool_node = ToolNode(self.tools)

        graph = StateGraph(self.state_schema)
        graph.add_node("call_model", self._call_model)
        graph.add_node("tool_node", tool_node)

        graph.add_edge(START, "call_model")
        graph.add_conditional_edges(
            "call_model",
            self._should_continue,
            {True: "tool_node", False: END},
        )
        graph.add_edge("tool_node", "call_model")

        return graph.compile(recursion_limit=self.recursion_limit)
