"""Tools for the Legislation Finder agent (Agent 1).

Contains: web_search, reliability_analysis.
All tools return Command objects to update LangGraph state.

Uses the official Brave Search MCP server (via Smithery) with Goggles.
"""

import json
from functools import lru_cache
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from config.system_prompts import reliability_judgment_prompt
from utils.tools import search_entity, get_org_classification
from utils.mcp.brave_client import search_legislation, extract_search_results
from utils.json_utils import extract_json
from utils.llm import get_mini_llm


@lru_cache(maxsize=1)
def _get_mini_model():
    return get_mini_llm()


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
    max_results: int = 5,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses the Brave Search MCP with Goggles optimized for legislation search.
    Prioritizes official government sites, legislative databases, and authoritative
    news sources. Filters out social media, blogs, and opinion pieces.

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
                        content=(summary),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except ValueError as e:
        error_msg = f"Brave Search API key not configured: {e}"
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
def reliability_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
    raw_legislation_sources: Annotated[
        list[dict[str, Any]], InjectedState("raw_legislation_sources")
    ],
) -> Command:
    """Analyze raw legislation sources for reliability using Wikidata organization lookup.

    Steps:
    1. Extract the true parent organization behind each source URL (LLM call).
    2. Look up each organization on Wikidata to get structured classification data.
    3. Make a reliability judgment using the Wikidata context (LLM call).
    4. Promote accepted sources to reliable_legislation_sources.

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

    sources_with_context = []

    for item in raw_legislation_sources:
        url = item.get("url", "Unknown URL")
        org_name = item.get("organization", "Unknown")

        wikidata_context = {"label": org_name, "description": "Not found on Wikidata"}

        if org_name and org_name != "Unknown":
            try:
                entity_id = search_entity(org_name)
                if entity_id:
                    wikidata_context = get_org_classification(entity_id)
            except Exception as e:
                print(f"[WARN] Wikidata lookup failed for {org_name}: {e}")
                wikidata_context = {"label": org_name, "description": "Lookup failed"}

        sources_with_context.append(
            {
                "url": url,
                "organization": org_name,
                "wikidata": wikidata_context,
            }
        )

    context_text = json.dumps(sources_with_context, indent=2, default=str)
    judgment_prompt = reliability_judgment_prompt.format(
        input_city=city, sources_with_context=context_text
    )

    judgment_response = _get_mini_model().invoke(
        [
            {"role": "system", "content": judgment_prompt},
            {
                "role": "user",
                "content": "Judge the reliability of each source based off of the context from Wikidata.",
            },
        ]
    )

    try:
        cleaned_content = extract_json(judgment_response.content)
        judgments = json.loads(cleaned_content)
    except (json.JSONDecodeError, TypeError) as e:
        # Safe fallback: reject all sources if judgment parsing fails (can't verify reliability)
        print(f"[DEBUG] JSON parse error: {e}")
        print(f"[DEBUG] Raw response: {judgment_response.content[:500]}...")
        summary = (
            f"Reliability analysis could not parse LLM judgments. "
            f"Falling back to rejecting all {len(raw_legislation_sources)} source(s)."
        )
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": [],
                "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            }
        )

    accepted = [j for j in judgments if j.get("accepted", False)]
    rejected = [j for j in judgments if not j.get("accepted", False)]
    reliable_sources = [j["url"] for j in accepted]

    summary_lines = [
        f"Reliability analysis complete. {len(accepted)} accepted, {len(rejected)} rejected.",
        "",
        "Accepted sources:" if accepted else "No sources accepted.",
    ]
    for j in accepted:
        summary_lines.append(f"  ✓ {j['url']} — {j.get('reason', 'No reason given')}")
    if rejected:
        summary_lines.append("Rejected sources:")
        for j in rejected:
            summary_lines.append(
                f"  ✗ {j['url']} — {j.get('reason', 'No reason given')}"
            )

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
