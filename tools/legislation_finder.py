"""Tools for the Legislation Finder agent (Agent 1).

Contains: web_search, reliability_analysis.
All tools return Command objects to update LangGraph state.
"""

import os
import json
from typing import Annotated, Any

import requests
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.prompts import reliability_judgment_prompt
from utils.tools import search_entity, get_org_classification
from utils.json_utils import extract_json

load_dotenv()
mini_model = ChatOpenAI(
    model="gpt-4o-mini", temperature=0.0, max_tokens=1500, timeout=30
)


@tool
def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: int = 5,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses the SerpApi to find recent, relevant legislation pages.

    Args:
        query: The search query — e.g. "recent Austin city council bylaws 2026".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with search results.
    """
    serp_api_key = os.getenv("SERP_API_KEY")

    if not serp_api_key:
        raise Exception("SERP API Key is invalid")

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "num": max_results,
                "api_key": serp_api_key,
                "engine": "google",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("organic_results", [])

        raw_legislation_sources = []
        for result in results[:max_results]:
            raw_legislation_sources.append(
                {
                    "organization": result.get("source", "Unknown"),
                    "url": result.get("link", "N/A"),
                }
            )

        summary = (
            f"Web search for '{query}' returned {len(raw_legislation_sources)} result(s):\n"
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
            entity_id = search_entity(org_name)
            if entity_id:
                wikidata_context = get_org_classification(entity_id)

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

    judgment_response = mini_model.invoke(
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
