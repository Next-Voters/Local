"""Wikidata API client for organization lookup and entity classification.

Provides direct HTTP access to the Wikidata API and SPARQL endpoint for
organization lookup and entity classification. Used by Agent 1 tools
(reliability_analysis, reflection_tool) to ground-truth sources against
structured knowledge.

Functions match the MCP server's tool interface:
    - search_entity(query) -> entity ID
    - search_property(query) -> property ID
    - get_entity_properties(entity_id) -> list of property IDs
    - get_metadata(entity_id) -> {label, description}
    - execute_sparql(sparql_query) -> list of result bindings
    - get_org_classification(entity_id) -> structured org type data
"""

import httpx

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NextVotersLocal/1.0 (https://github.com/next-voters-local; contact@nextvoters.local) httpx/0.27",
}


def search_entity(query: str) -> str | None:
    """Search for a Wikidata entity ID by name.

    Args:
        query: The entity name to search for (e.g., "City of Austin", "Heritage Foundation").

    Returns:
        The Wikidata entity ID (e.g., "Q2621") or None if not found.
    """
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


def search_property(query: str) -> str | None:
    """Search for a Wikidata property ID by name.

    Args:
        query: The property name to search for (e.g., "instance of", "country").

    Returns:
        The Wikidata property ID (e.g., "P31") or None if not found.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 120,
        "srlimit": 1,
        "srqiprofile": "classic",
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


def get_entity_properties(entity_id: str) -> list[str]:
    """Get all property IDs associated with a Wikidata entity.

    Args:
        entity_id: A valid Wikidata entity ID (e.g., "Q2621").

    Returns:
        List of property IDs (e.g., ["P31", "P17", "P856"]).
    """
    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "claims",
        "format": "json",
    }
    response = httpx.get(WIKIDATA_API_URL, headers=HEADERS, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    return list(data.get("entities", {}).get(entity_id, {}).get("claims", {}).keys())


def get_metadata(entity_id: str, language: str = "en") -> dict[str, str]:
    """Get the label and description for a Wikidata entity.

    Args:
        entity_id: A valid Wikidata entity ID.
        language: ISO 639-1 language code (default "en").

    Returns:
        Dict with "label" and "description" keys.
    """
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


def execute_sparql(sparql_query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata's query service.

    Args:
        sparql_query: A valid SPARQL query string.

    Returns:
        List of result binding dicts from the SPARQL response.
    """
    response = httpx.get(
        WIKIDATA_SPARQL_URL,
        params={"query": sparql_query, "format": "json"},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


def get_org_classification(entity_id: str) -> dict:
    """Get structured organization classification data from Wikidata.

    Queries for the entity's type (instance of), country, official website,
    and parent organization — the key properties needed to classify an
    organization as government, media, think tank, nonprofit, etc.

    Args:
        entity_id: A valid Wikidata entity ID (e.g., "Q2621").

    Returns:
        Dict with keys: label, description, instance_of (list), country,
        official_website, parent_org. Values are strings or lists of strings.
    """
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
        results = execute_sparql(sparql)
    except Exception:
        return get_metadata(entity_id)

    metadata = get_metadata(entity_id)

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
