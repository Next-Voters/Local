"""Tools for the Legislation Finder agent (Agent 1).

Contains: web_search, reliability_analysis.
All tools return Command objects to update LangGraph state.
"""

import os
import json
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command
from tavily import TavilyClient

from utils.prompts import (
    reliability_org_extraction_prompt,
    reliability_judgment_prompt,
)
from utils.wikidata_client import search_entity, get_org_classification

load_dotenv()

mini_model = ChatOpenAI(
    model="gpt-5-mini", temperature=0.0, max_tokens=1500, timeout=30
)

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for legislation related to a specific municipality or topic.

    Uses the Tavily search API to find recent, relevant legislation pages.

    Args:
        query: The search query — e.g. "recent Austin city council bylaws 2026".
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
            response.get("results", []),
            key=lambda x: x.get("score", 0.0),
            reverse=True,
        )[:5]

        new_formatted_results = []
        for result in sorted_results:
            new_formatted_results.append(
                f"Title: {result.get('title', 'N/A')}\n"
                f"URL: {result.get('url', 'N/A')}\n"
                f"Content: {result.get('content', 'N/A')[:500]}\n"
                f"Score: {result.get('score', 0.0)}\n"
            )

        return Command(update={"raw_legislation_sources": new_formatted_results})

    except Exception as e:
        return f"Error performing search: {str(e)}"


@tool
def reliability_analysis(
    raw_legislation_sources: Annotated[
        list[str], InjectedState("raw_legislation_sources")
    ],
) -> Command:
    """Analyze raw legislation sources for reliability using Wikidata organization lookup.

    Steps:
    1. Extract the true parent organization behind each source URL (LLM call).
    2. Look up each organization on Wikidata to get structured classification data.
    3. Make a reliability judgment using the Wikidata context (LLM call).
    4. Promote accepted sources to reliable_legislation_sources.

    Returns:
        A Command that updates reliable_legislation_sources with accepted sources
        and clears raw_legislation_sources.
    """
    if not raw_legislation_sources:
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": [],
            }
        )

    # Step 1: Extract parent organizations from source URLs via LLM
    sources_text = "\n---\n".join(raw_legislation_sources)
    extraction_prompt = reliability_org_extraction_prompt.format(sources=sources_text)

    extraction_response = mini_model.invoke(
        [
            {"role": "system", "content": extraction_prompt},
            {
                "role": "user",
                "content": "Extract the parent organization for each source.",
            },
        ]
    )

    try:
        org_extractions = json.loads(extraction_response.content)
    except (json.JSONDecodeError, TypeError):
        # If extraction fails, pass all sources through as unknown
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": raw_legislation_sources,
            }
        )

    # Step 2: Look up each organization on Wikidata
    sources_with_context = []
    for item in org_extractions:
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

    # Step 3: Make reliability judgment via LLM using Wikidata context
    context_text = json.dumps(sources_with_context, indent=2, default=str)
    judgment_prompt = reliability_judgment_prompt.format(
        sources_with_context=context_text
    )

    judgment_response = mini_model.invoke(
        [
            {"role": "system", "content": judgment_prompt},
            {"role": "user", "content": "Judge the reliability of each source."},
        ]
    )

    try:
        judgments = json.loads(judgment_response.content)
    except (json.JSONDecodeError, TypeError):
        # If judgment fails, pass all sources through
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": raw_legislation_sources,
            }
        )

    # Step 4: Filter accepted sources — match back to raw_legislation_sources
    accepted_urls = {j["url"] for j in judgments if j.get("accepted", False)}

    reliable_sources = []
    for source in raw_legislation_sources:
        for accepted_url in accepted_urls:
            if accepted_url in source:
                reliable_sources.append(source)
                break

    return Command(
        update={
            "raw_legislation_sources": [],
            "reliable_legislation_sources": reliable_sources,
        }
    )
