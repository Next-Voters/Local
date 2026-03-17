from typing import Callable, Union, TypeVar, Type
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from utils.schemas import ReflectionEntry, BaseAgentState
from tools.base_agent_tools import reflection_tool

load_dotenv()

StateType = TypeVar("StateType")

_REFLECTION_PREAMBLE = "Here are previous reflections. Use as context to drive your next actions/decisions:\n\n"


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
    ):
        self.state_schema = state_schema
        # Always include reflection_tool by default
        self.tools = [reflection_tool] + tools
        self.system_prompt = system_prompt

        self.model = ChatOpenAI(
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

        return graph.compile()
