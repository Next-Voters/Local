"""Tools for the Legislation Finder agent (Agent 1).

Contains: web_search, reliability_analysis.
All tools return Command objects to update LangGraph state.
"""

import os
import json
from typing import Annotated

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.prompts import reliability_judgment_prompt
from utils.wikidata_client import search_entity, get_org_classification


load_dotenv()
mini_model = ChatOpenAI(
    model="gpt-5-mini", temperature=0.0, max_tokens=1500, timeout=30
)


@tool
def web_search(query: str, max_results: int = 5) -> Command | str:
    """Search the web for legislation related to a specific municipality or topic.

    Uses the SerpApi to find recent, relevant legislation pages.

    Args:
        query: The search query — e.g. "recent Austin city council bylaws 2026".
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

        return Command(update={"raw_legislation_sources": raw_legislation_sources})

    except Exception as e:
        return f"Error: ${e}"


@tool
def reliability_analysis(
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
        sources_with_context=context_text
    )

    judgment_response = mini_model.invoke(
        [
            {"role": "system", "content": judgment_prompt},
            {"role": "user", "content": "Judge the reliability of each source based off of the context from Wikidata."},
        ]
    )

    try:
        judgments = json.loads(judgment_response.content)
    except (json.JSONDecodeError, TypeError):
        return Command(
            update={
                "raw_legislation_sources": [],
                "reliable_legislation_sources": raw_legislation_sources,
            }
        )

    reliable_sources = {j["url"] for j in judgments if j.get("accepted", False)}

    return Command(
        update={
            "raw_legislation_sources": [],
            "reliable_legislation_sources": reliable_sources,
        }
    )
