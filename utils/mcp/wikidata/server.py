"""Wikidata MCP server — runs as a standalone stdio subprocess.

This file is NOT imported by app code. It is launched by client.py as a
subprocess. Provides FastMCP tools wrapping Wikidata API/SPARQL lookups
and an LLM-based reliability judgment pipeline.

Usage: python -m utils.mcp.wikidata.server
"""

import json
import os
import sys
from pathlib import Path

import httpx
from fastmcp import FastMCP
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.system_prompts import reliability_judgment_prompt

mcp = FastMCP("Wikidata")

# ---------------------------------------------------------------------------
# Wikidata HTTP helpers
# ---------------------------------------------------------------------------

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NextVotersLocal/1.0 (https://github.com/next-voters-local; contact@nextvoters.local) httpx/0.27",
}


def _search_entity(query: str) -> str | None:
    """Search for a Wikidata entity ID by name."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 0,
        "srlimit": 1,
        "srqiprofile": "classic_noboostlinks",
        "srwhat": "text",
        "format": "json",
    }
    response = httpx.get(WIKIDATA_API_URL, headers=HEADERS, params=params, timeout=15)
    response.raise_for_status()
    try:
        title = response.json()["query"]["search"][0]["title"]
        return title.split(":")[-1]
    except (KeyError, IndexError):
        return None


def _get_metadata(entity_id: str, language: str = "en") -> dict[str, str]:
    """Get the label and description for a Wikidata entity."""
    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "labels|descriptions",
        "languages": language,
        "format": "json",
    }
    response = httpx.get(WIKIDATA_API_URL, headers=HEADERS, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    entity_data = data.get("entities", {}).get(entity_id, {})
    label = entity_data.get("labels", {}).get(language, {}).get("value", "Unknown")
    description = (
        entity_data.get("descriptions", {})
        .get(language, {})
        .get("value", "No description available")
    )
    return {"label": label, "description": description}


def _execute_sparql(sparql_query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata."""
    response = httpx.get(
        WIKIDATA_SPARQL_URL,
        params={"query": sparql_query, "format": "json"},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def _get_org_classification(entity_id: str) -> dict:
    """Get structured organization classification data from Wikidata."""
    sparql = f"""
    SELECT ?instanceOfLabel ?countryLabel ?website ?parentOrgLabel ?description WHERE {{
      OPTIONAL {{ wd:{entity_id} wdt:P31 ?instanceOf. }}
      OPTIONAL {{ wd:{entity_id} wdt:P17 ?country. }}
      OPTIONAL {{ wd:{entity_id} wdt:P856 ?website. }}
      OPTIONAL {{ wd:{entity_id} wdt:P749 ?parentOrg. }}
      OPTIONAL {{ wd:{entity_id} schema:description ?description. FILTER(LANG(?description) = "en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 20
    """
    try:
        results = _execute_sparql(sparql)
    except Exception:
        return _get_metadata(entity_id)

    metadata = _get_metadata(entity_id)

    instance_of_set = set()
    country = None
    website = None
    parent_org = None

    for row in results:
        if "instanceOfLabel" in row:
            instance_of_set.add(row["instanceOfLabel"]["value"])
        if "countryLabel" in row and not country:
            country = row["countryLabel"]["value"]
        if "website" in row and not website:
            website = row["website"]["value"]
        if "parentOrgLabel" in row and not parent_org:
            parent_org = row["parentOrgLabel"]["value"]

    return {
        "label": metadata["label"],
        "description": metadata["description"],
        "instance_of": list(instance_of_set),
        "country": country,
        "official_website": website,
        "parent_org": parent_org,
    }


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool
def search_entity(query: str) -> dict:
    """Search for a Wikidata entity ID by name.

    Args:
        query: The entity name to search for (e.g., "City of Austin").

    Returns:
        Dict with "entity_id" (string or null).
    """
    entity_id = _search_entity(query)
    return {"entity_id": entity_id}


@mcp.tool
def get_org_classification(entity_id: str) -> dict:
    """Get structured organization classification data from Wikidata.

    Queries for the entity's type (instance of), country, official website,
    and parent organization.

    Args:
        entity_id: A valid Wikidata entity ID (e.g., "Q2621").

    Returns:
        Dict with label, description, instance_of, country, official_website,
        parent_org.
    """
    return _get_org_classification(entity_id)


@mcp.tool
def analyze_reliability(sources: list[dict], city: str) -> dict:
    """Analyze source reliability using Wikidata lookups and LLM judgment.

    For each source, looks up the organization on Wikidata to get structured
    classification data, then uses an LLM to make a reliability judgment.

    Args:
        sources: List of dicts with "url" and "organization" keys.
        city: The city to evaluate sources against.

    Returns:
        Dict with "judgments" list, each containing url, organization, tier,
        rationale, and accepted boolean.
    """
    if not sources:
        return {"judgments": []}

    # Enrich sources with Wikidata context
    sources_with_context = []
    for item in sources:
        url = item.get("url", "Unknown URL")
        org_name = item.get("organization", "Unknown")

        wikidata_context = {"label": org_name, "description": "Not found on Wikidata"}

        if org_name and org_name != "Unknown":
            try:
                entity_id = _search_entity(org_name)
                if entity_id:
                    wikidata_context = _get_org_classification(entity_id)
            except Exception as e:
                wikidata_context = {"label": org_name, "description": f"Lookup failed: {e}"}

        sources_with_context.append(
            {
                "url": url,
                "organization": org_name,
                "wikidata": wikidata_context,
            }
        )

    # Build prompt and call LLM
    context_text = json.dumps(sources_with_context, indent=2, default=str)
    judgment_prompt = reliability_judgment_prompt.format(
        input_city=city, sources_with_context=context_text
    )

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    # Define the JSON schema for structured output
    response_schema = {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "organization": {"type": "string"},
                        "tier": {
                            "type": "string",
                            "enum": [
                                "highly_reliable",
                                "conditionally_reliable",
                                "unreliable",
                                "unknown",
                            ],
                        },
                        "rationale": {"type": "string"},
                        "accepted": {"type": "boolean"},
                    },
                    "required": [
                        "url",
                        "organization",
                        "tier",
                        "rationale",
                        "accepted",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["judgments"],
        "additionalProperties": False,
    }

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": judgment_prompt},
            {
                "role": "user",
                "content": "Judge the reliability of each source based off of the context from Wikidata.",
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "reliability_analysis",
                "schema": response_schema,
                "strict": True,
            }
        },
    )

    return json.loads(response.output_text)


if __name__ == "__main__":
    mcp.run(transport="stdio")
