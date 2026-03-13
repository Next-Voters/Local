import operator
from datetime import datetime, timedelta
from dotenv import load_dotenv

from typing import TypedDict, Annotated, NotRequired

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from utils.models import ReflectionEntry
from utils.prompts import legislation_finder_sys_prompt
from tools.legislation_finder import web_search, reflection_tool, reliability_analysis

load_dotenv()

model = ChatOpenAI(model="gpt-4o", temperature=0.0, max_tokens=2000, timeout=30)


class LegislationFinderState(TypedDict):
    """State for the legislation finder agent."""

    messages: Annotated[list[BaseMessage], operator.add]
    reflection_list: NotRequired[Annotated[list[ReflectionEntry], operator.add]]
    city: NotRequired[str]

    raw_legislation_sources: NotRequired[Annotated[list[str], operator.add]]
    reliable_legislation_sources: NotRequired[Annotated[list[str], operator.add]]


# === TOOL LIST ===

tools = [web_search, reflection_tool, reliability_analysis]


# === FUNCTIONS FOR NODES ===
def should_continue(state: LegislationFinderState) -> bool:
    """Determine if the agent should continue or end based on if there is a tool call to be made."""
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return True

    return False


def call_model(state: LegislationFinderState) -> LegislationFinderState:
    """Call the LLM with the current state, including reflection context."""
    messages = state["messages"]
    city = state.get("city", "Unknown")
    reflection_list = state.get("reflection_list", [])

    parsed_reflection_list = "\n".join(
        [
            f"{r.reflection}"
            f"\n  Gaps: {', '.join(r.gaps_identified) or 'None'}"
            f"\n  Next action: {r.next_action}"
            for r in reflection_list
        ]
    )

    system_prompt = legislation_finder_sys_prompt.format(
        input_city=city,
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d"),
        today=datetime.today().strftime("%B %d"),
        reflections=parsed_reflection_list,
    )

    model_with_tools = model.bind_tools(tools)

    response = model_with_tools.invoke(
        [{"role": "system", "content": system_prompt}] + messages
    )

    return {"messages": [response]}


process_tools = ToolNode(tools)


def build_legislation_finder_agent():
    """Build and return the compiled legislation finder agent graph.

    This is a low-level LangGraph ReAct agent that:
    1. Takes a city as input
    2. Conducts web searches for legislation
    3. Uses reflection_tool to analyze and store reflections
    4. Runs reliability_analysis to filter sources via Wikidata
    5. Returns findings with authoritative sources

    Returns:
        A compiled LangGraph that can be invoked with state.
    """

    graph = StateGraph(LegislationFinderState)

    graph.add_node("call_model", call_model)
    graph.add_node("tool_node", process_tools)

    graph.add_edge(START, "call_model")
    graph.add_conditional_edges(
        "call_model",
        should_continue,
        {
            True: "tool_node",
            False: END,
        },
    )
    graph.add_edge("tool_node", "call_model")

    return graph.compile()


legislation_finder_agent = build_legislation_finder_agent()
