"""Legislation finder agent for NV Local.

This module defines the legislation_finder_agent that researches local legislation
for a given city. It uses the BaseReActAgent template with web search and
reliability analysis tools.

The agent searches for recent local legislation and evaluates source reliability.
It uses a dynamic system prompt that incorporates the target city and date range.

Tools are thin adapters that call MCP servers and wrap results in LangGraph Commands.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from agents.base_agent_template import BaseReActAgent
from utils.mcp.tavily import search_legislation, extract_search_results
from utils.mcp.wikidata import analyze_reliability as mcp_analyze_reliability
from utils.schemas import LegislationFinderState
from config.system_prompts import legislation_finder_sys_prompt


# ---------------------------------------------------------------------------
# Tool adapters (MCP call → LangGraph Command)
# ---------------------------------------------------------------------------


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
    max_results: int = 5,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses Tavily search with a legislation profile to prioritize official government
    sites, legislative databases, and authoritative news sources.

    Args:
        query: The search query — e.g. "Austin city council bylaws March 2026" or
               "municipal ordinance zoning city council passed".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with search results.
    """
    try:
        raw_results = await search_legislation(
            query=query,
            city=city,
            max_results=max_results,
        )

        results = extract_search_results(raw_results)

        raw_legislation_sources = []
        for result in results:
            raw_legislation_sources.append(
                {
                    "organization": result.get("title", "Unknown"),
                    "url": result.get("url", "N/A"),
                }
            )

        summary = (
            f"Web search for '{query}' (city: {city}) returned {len(raw_legislation_sources)} result(s):\n"
            + "\n".join(
                f"  - {s['organization']}: {s['url']}" for s in raw_legislation_sources
            )
        )

        return Command(
            update={
                "raw_legislation_sources": raw_legislation_sources,
                "messages": [
                    ToolMessage(
                        content=summary,
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except ValueError as e:
        error_msg = f"Tavily API key not configured: {e}"
        return Command(
            update={
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )
    except Exception as e:
        error_msg = f"Web search failed: {e}"
        return Command(
            update={
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


@tool
async def reliability_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
    raw_legislation_sources: Annotated[
        list[dict[str, Any]], InjectedState("raw_legislation_sources")
    ],
) -> Command:
    """Analyze raw legislation sources for reliability using Wikidata organization lookup.

    Delegates to the Wikidata MCP server which performs Wikidata lookups and
    LLM-based reliability classification.

    Args:
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        raw_legislation_sources: Injected from state — sources to evaluate.

    Returns:
        A Command that updates reliable_legislation_sources with accepted sources
        and clears raw_legislation_sources.
    """
    if not raw_legislation_sources:
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": [],
                "messages": [
                    ToolMessage(
                        content="Reliability analysis skipped: no raw sources to evaluate.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    try:
        result = await mcp_analyze_reliability(
            sources=raw_legislation_sources, city=city
        )

        judgments = result.get("judgments", [])
        accepted = [j for j in judgments if j.get("accepted") and j.get("url")]
        rejected = [j for j in judgments if not j.get("accepted") or not j.get("url")]
        reliable_sources = [j["url"] for j in accepted]

        summary_lines = [
            f"Reliability analysis complete. {len(accepted)} accepted, {len(rejected)} rejected.",
            "",
            "Accepted sources:" if accepted else "No sources accepted.",
        ]
        for j in accepted:
            summary_lines.append(f"  ✓ {j['url']} — {j.get('rationale', '')}")
        if rejected:
            summary_lines.append("Rejected sources:")
            for j in rejected:
                summary_lines.append(f"  ✗ {j.get('url', 'N/A')} — {j.get('rationale', '')}")

        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": reliable_sources,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        error_msg = f"Reliability analysis failed: {e}"
        return Command(
            update={
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=LegislationFinderState,
    tools=[
        web_search,
        reliability_analysis
    ],
    system_prompt=lambda state: legislation_finder_sys_prompt.format(
        input_city=state.get("city", "Unknown"),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
        today=datetime.today().strftime("%B %d, %Y"),
    ),
)

legislation_finder_agent = _agent.build()
