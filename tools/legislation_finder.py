"""Tools for the Legislation Finder agent (Agent 1).

Contains: web_search, reliability_analysis.
All tools return Command objects to update LangGraph state.

Uses Tavily cloud search with profile-based customization.
"""

import json
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from config.system_prompts import reliability_judgment_prompt
from utils.tools import search_entity, get_org_classification
from utils.mcp.tavily_client import search_legislation, extract_search_results
from utils.llm import get_structured_mini_llm
from utils.schemas import ReliabilityAnalysisResult

load_dotenv()

_reliability_model = get_structured_mini_llm(ReliabilityAnalysisResult)


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
                        content=(summary),
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

    result = _reliability_model.invoke(
        [
            {"role": "system", "content": judgment_prompt},
            {
                "role": "user",
                "content": "Judge the reliability of each source based off of the context from Wikidata.",
            },
        ]
    )

    accepted = [judgement for judgement in result.judgments if judgement.accepted and judgement.url]
    rejected = [judgement for judgement in result.judgments if not judgement.accepted or not judgement.url]
    reliable_sources = [judgement.url for judgement in accepted]

    summary_lines = [
        f"Reliability analysis complete. {len(accepted)} accepted, {len(rejected)} rejected.",
        "",
        "Accepted sources:" if accepted else "No sources accepted.",
    ]
    for judgement in accepted:
        summary_lines.append(f"  ✓ {judgement.url} — {judgement.rationale}")
    if rejected:
        summary_lines.append("Rejected sources:")
        for judgement in rejected:
            summary_lines.append(f"  ✗ {judgement.url} — {judgement.rationale}")

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
