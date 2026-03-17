"""Political figure finder API clients for Canadian and American political data."""

from typing import Any

import requests


def detect_country_from_city(city: str) -> str:
    """Detect country code from a city name using Nominatim geocoding.

    Uses the OpenStreetMap Nominatim API to resolve a city name to its
    country code (e.g., "Toronto" -> "CA", "Chicago" -> "US").

    Args:
        city: The name of the city to geocode.

    Returns:
        The uppercase two-letter country code (e.g., "CA", "US").

    Raises:
        ValueError: If the city is not found or has no country code.
        requests.HTTPError: If the API request fails.
    """
    nominatim_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": "PoliticalCommentaryAgent/1.0"}

    response = requests.get(nominatim_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    if not data:
        raise ValueError(f"City '{city}' not found")

    return data[0].get("address", {}).get("country_code", "").upper()


def fetch_canadian_political_figures(city: str) -> list[dict[str, Any]]:
    """Fetch Canadian political figures using the Represent API.

    Queries the Represent API for federal, provincial, and municipal
    representatives for the given city.

    Args:
        city: The Canadian city name to search for political figures.

    Returns:
        A list of dicts, each containing name, position, party, jurisdiction,
        and source_url.

    Raises:
        requests.HTTPError: If the API request fails.
    """
    base_url = "https://represent.opennorth.ca/representatives/"
    params = {
        "city": city,
        "limit": 20,
    }

    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    political_figures = []
    for item in data.get("objects", []):
        political_figures.append(
            {
                "name": item.get("name", ""),
                "position": item.get("elected_office", ""),
                "party": item.get("party_name", ""),
                "jurisdiction": item.get("district_name", ""),
                "source_url": item.get("source_url", ""),
            }
        )

    return political_figures


def fetch_american_political_figures(city: str) -> list[dict[str, Any]]:
    """Fetch American political figures using the We Vote API.

    Queries the We Vote API for political candidates in the given city
    for the current election year.

    Args:
        city: The American city name to search for political figures.

    Returns:
        A list of dicts, each containing name, position, party, jurisdiction,
        and source_url.

    Raises:
        requests.HTTPError: If the API request fails.
    """
    we_vote_base_url = "https://api.wevoteusa.org/apis/v1/candidatesQuery"

    current_year = "2026"
    params = {
        "electionDay": current_year,
        "searchText": city,
    }

    response = requests.get(we_vote_base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    political_figures = []
    for item in data.get("candidates", []):
        political_figures.append(
            {
                "name": f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                "position": item.get("office_name", ""),
                "party": item.get("party", ""),
                "jurisdiction": item.get("state_code", ""),
                "source_url": item.get("ballotpedia_candidate_url", ""),
            }
        )

    return political_figures
