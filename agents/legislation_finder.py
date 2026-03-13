import os
import json
import operator
from datetime import datetime, timedelta
from dotenv import load_dotenv

from typing import TypedDict, Annotated, NotRequired
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from tavily import TavilyClient

from utils.prompts import (
    legislation_finder_sys_prompt,
    reliability_org_extraction_prompt,
    reliability_judgment_prompt,
    reflection_prompt,
)
from utils.wikidata_client import search_entity, get_org_classification

load_dotenv()

model = ChatOpenAI(model="gpt-4o", temperature=0.0, max_tokens=2000, timeout=30)
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

class ReflectionEntry(BaseModel):
    """State for all reflection that agent conducts"""

    reflection: str = Field(
        description="Based on the current conversation that you have had, build a complete, but succinct reflection to create enriched context for agent"
    )
    gaps_identified: list[str] = Field(
        default_factory=list,
        description="Information gaps or missing context that needs to be addressed",
    )
    next_action: str = Field(
        description="Specific action planned for the next iteration (e.g., search query, tool to use)"
    )


class IndividualReliabilityAnalysis(BaseModel):
    """State for all individual reliability analysis"""

    score: str = Field(
        description="Assign a score on how reliable the source is. Look for .edu .gov and city sources like brampton.ca when giving a score. Create a bias towards government ran websites to ensure non-partisian involvement."
    )
    rationale: str = Field(
        description="Explain your choice for the scoring in 250 characters or less"
    )


class LegislationFinderState(TypedDict):
    """State for the legislation finder agent."""

    messages: Annotated[list[BaseMessage], operator.add]
    reflection_list: NotRequired[Annotated[list[ReflectionEntry], operator.add]]
    city: NotRequired[str]

    raw_legislation_sources: NotRequired[Annotated[list[str], operator.add]]
    reliable_legislation_sources: NotRequired[Annotated[list[str], operator.add]]

class LegislationJudgement(BaseModel):
    pass

# === TOOLS ===

tools = [web_search, reflection_tool, reliability_analysis]
tool_lookup = {tool.name: tool for tool in tools}


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
            f"\n  Findings: {', '.join(r.key_findings) or 'None'}"
            f"\n  Gaps: {', '.join(r.gaps_identified) or 'None'}"
            f"\n Next Actions/Tool Calls: {', '.join(r.next_actions) or 'None yet'}"
            for r in reflection_list
        ]
    )

    system_prompt = legislation_finder_sys_prompt.format(
        input_city=city,
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d"),
        today_date=datetime.today().strftime("%B %d"),
        reflections=parsed_reflection_list,
    )

    model_with_tools = model.bind_tools(tools)

    response = model_with_tools.invoke(
        [{"role": "system", "content": system_prompt}] + messages
    )

    return {"messages": messages + [response]}


process_tools = ToolNode(tools)


def build_legislation_finder_agent():
    """Build and return the compiled legislation finder agent graph.

    This is a low-level LangGraph ReAct agent that:
    1. Takes a city as input
    2. Conducts web searches for legislation
    3. Uses reflection_tool to analyze and store reflections
    4. Returns findings with authoritative sources

    The reflection_tool is callable by the agent and stores reflections in reflection_list.

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
    graph.add_edge("process_tools", "call_model")

    return graph.compile()


legislation_finder_agent = build_legislation_finder_agent()
