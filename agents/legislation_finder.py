import os
import operator
from dotenv import load_dotenv

from typing import TypedDict, Annotated, NotRequired
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from tavily import TavilyClient

from utils.prompts import legislation_finder_sys_prompt

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


class LegislationFinderState(TypedDict):
    """State for the legislation finder agent."""

    messages: Annotated[list[BaseMessage], operator.add]
    reflection_list: NotRequired[Annotated[list[ReflectionEntry], operator.add]]
    city: NotRequired[str]
    legislation_sources: NotRequired[Annotated[list[str], operator.add]]


# === TOOLS ===
@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for legislation related to a specific municipality or topic.

    Uses the Tavily search API to find recent, relevant legislation pages.

    Args:
        query: The search query — e.g. "recent Brampton city council bylaws 2026".
        max_results: Maximum number of results to return (default 5).

    Returns:
        A formatted string with search results including titles, URLs, and content snippets.
    """
    try:
        response = tavily_client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_answer=False,
            include_raw_content=True,
        )

        if not response.get("results"):
            return f"No results found for query: {query}"

        sorted_results = sorted(
            response.get("results", []), key=lambda x: x.get("score", 0.0), reverse=True
        )[:5]
        top_urls = [result.get("url") for result in sorted_results if result.get("url")]

        new_formatted_results = []
        for result in sorted_results:
            new_formatted_results.append(
                f"Title: {result.get('title', 'N/A')}\n"
                f"URL: {result.get('url', 'N/A')}\n"
                f"Content: {result.get('content', 'N/A')[:500]}\n"
                f"Score: {result.get('score', 0.0)}\n"
            )

        return Command(
            update={"legislation_sources", new_formatted_results}
        )

    except Exception as e:
        return f"Error performing search: {str(e)}"


@tool
def reflection_tool(reflection: ReflectionEntry) -> str:
    """Generate a reflection on the current progress and next steps.

    Args:
        reflection: A structured ReflectionEntry containing the agent's reflection,
            identified gaps, planned next action, and confidence score.

    Returns:
        A Command that updates the graph state by appending the reflection to reflection_list.
    """
    return Command(
        update={"reflection_list": [reflection]}
    )


@tool
def reliability_analysis(analyses):
    return f"Reliability analysis: {analyses}"


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
