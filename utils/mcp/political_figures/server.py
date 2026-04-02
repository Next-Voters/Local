"""Political Figures MCP server — runs as a standalone stdio subprocess.

This file is NOT imported by app code. It is launched by client.py as a
subprocess. Provides FastMCP tools for finding political figures, extracting
commentary from web pages, and searching politician tweets via tweepy.

Usage: python -m utils.mcp.political_figures.server
"""

import datetime
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import requests
import tweepy
from fastmcp import FastMCP
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.system_prompts.political_commentary import comment_extraction_prompt

mcp = FastMCP("PoliticalFigures")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Twitter/X helpers
# ---------------------------------------------------------------------------

TWITTER_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,15}$")
SAFE_CONTEXT_REGEX = re.compile(r"[^\w\s\-.,!?']")


def _validate_twitter_handle(handle: str) -> tuple[bool, str]:
    """Validate a Twitter handle for safe use in queries."""
    if not handle:
        return False, ""
    sanitized = handle.strip().lstrip("@")
    if not sanitized:
        return False, ""
    if " " in sanitized or ":" in sanitized or "@" in sanitized:
        return False, ""
    if not TWITTER_HANDLE_REGEX.match(sanitized):
        return False, ""
    return True, sanitized


def _sanitize_search_context(context: str, max_length: int = 100) -> str:
    """Sanitize research context for safe use in Twitter search queries."""
    if not context:
        return ""
    sanitized = context.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = SAFE_CONTEXT_REGEX.sub("", sanitized)
    sanitized = sanitized.strip()[:max_length]
    return sanitized


def _get_twitter_client() -> tweepy.Client:
    """Get an authenticated tweepy Client using bearer token."""
    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not bearer_token:
        raise ValueError(
            "TWITTER_BEARER_TOKEN not set in environment. "
            "Get your token at https://developer.twitter.com/"
        )
    return tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=False)


def _extract_tweets_from_response(response: tweepy.Response | None) -> list[dict]:
    """Extract tweet dicts from a tweepy Response object."""
    if response is None or response.data is None:
        return []
    tweets = []
    for tweet in response.data:
        tweet_dict: dict[str, Any] = {
            "id": str(tweet.id),
            "text": tweet.text,
            "author_id": str(tweet.author_id) if tweet.author_id else None,
            "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
        }
        if hasattr(tweet, "public_metrics") and tweet.public_metrics:
            tweet_dict["public_metrics"] = tweet.public_metrics
        tweets.append(tweet_dict)
    return tweets


# ---------------------------------------------------------------------------
# Political figure API helpers
# ---------------------------------------------------------------------------


def _detect_country_from_city(city: str) -> str:
    """Detect country code from city name using Nominatim geocoding."""
    nominatim_url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "json", "limit": 1, "addressdetails": 1}
    headers = {"User-Agent": "PoliticalCommentaryAgent/1.0"}
    response = requests.get(nominatim_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise ValueError(f"City '{city}' not found")
    return data[0].get("address", {}).get("country_code", "").upper()


def _fetch_canadian_political_figures(city: str) -> list[dict[str, Any]]:
    """Fetch Canadian political figures using the Represent API."""
    base_url = "https://represent.opennorth.ca/representatives/"
    params = {"city": city, "limit": 20}
    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    figures = []
    for item in data.get("objects", []):
        figures.append(
            {
                "name": item.get("name", ""),
                "position": item.get("elected_office", ""),
                "party": item.get("party_name", ""),
                "jurisdiction": item.get("district_name", ""),
                "source_url": item.get("source_url", ""),
            }
        )
    return figures


def _fetch_american_political_figures(city: str) -> list[dict[str, Any]]:
    """Fetch American political figures using the We Vote API."""
    we_vote_base_url = "https://api.wevoteusa.org/apis/v1/candidatesQuery"
    current_year = str(datetime.date.today().year)
    params = {"electionDay": current_year, "searchText": city}
    response = requests.get(we_vote_base_url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    figures = []
    for item in data.get("candidates", []):
        figures.append(
            {
                "name": f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                "position": item.get("office_name", ""),
                "party": item.get("party", ""),
                "jurisdiction": item.get("state_code", ""),
                "source_url": item.get("ballotpedia_candidate_url", ""),
            }
        )
    return figures


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool
def find_political_figures(city: str) -> dict:
    """Find political figures (candidates, elected officials) for a city.

    Automatically detects whether the city is in Canada or the USA and queries
    the appropriate API (OpenNorth Represent for Canada, We Vote for USA).

    Args:
        city: The city name to search for political figures.

    Returns:
        Dict with "figures" (list of dicts) and "country" ("canada" or "usa").
    """
    try:
        country_code = _detect_country_from_city(city)
    except Exception as e:
        return {"error": f"Failed to detect country for '{city}': {e}", "figures": [], "country": None}

    if country_code not in ("CA", "US"):
        return {
            "error": f"Unsupported country: {country_code}. Only Canada (CA) and USA (US) are supported.",
            "figures": [],
            "country": None,
        }

    country = "canada" if country_code == "CA" else "usa"

    try:
        if country == "canada":
            figures = _fetch_canadian_political_figures(city)
        else:
            figures = _fetch_american_political_figures(city)
        return {"figures": figures, "country": country}
    except Exception as e:
        return {"error": f"Failed to find political figures: {e}", "figures": [], "country": country}


@mcp.tool
def extract_commentary(url: str, politician: str, query: str) -> dict:
    """Extract political commentary from a web page using LLM analysis.

    Fetches the page content and uses an LLM to extract statements or
    commentary made by the specified politician.

    Args:
        url: The URL of the page to extract commentary from.
        politician: The name of the politician to find commentary for.
        query: The search query context for the extraction.

    Returns:
        Dict with "commentary" key containing the extracted text.
    """
    # Fetch page content
    try:
        headers = {
            "User-Agent": "PoliticalCommentaryAgent/1.0",
            "Accept": "text/html,application/xhtml+xml",
        }
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        page_content = response.text[:15000]
    except Exception as e:
        return {"commentary": f"Failed to fetch content: {e}"}

    # Extract commentary with LLM
    system_prompt = comment_extraction_prompt.format(politician=politician, query=query)
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Page content:\n\n{page_content}"},
            ],
        )
        return {"commentary": response.output_text.strip()}
    except Exception as e:
        return {"commentary": f"Failed to extract commentary: {e}"}


@mcp.tool
def search_politician_tweets(
    politician_name: str,
    city: str = "",
    research_context: str = "",
    max_results: int = 10,
) -> dict:
    """Search for a politician's tweets on Twitter/X.

    Attempts to find the politician's Twitter account by trying common handle
    formats, then retrieves their tweets filtered by city and context.

    Args:
        politician_name: The full name of the politician to search for.
        city: The city to filter tweets by.
        research_context: Additional context for filtering tweets.
        max_results: Maximum number of tweets to retrieve.

    Returns:
        Dict with "user_found" (bool), "verified_username" (str or null),
        "tweets" (list of tweet dicts), and optional "error".
    """
    if not politician_name or not politician_name.strip():
        return {
            "error": "Politician name is required",
            "user_found": False,
            "tweets": [],
        }

    tweet_fields = ["id", "text", "author_id", "created_at", "public_metrics"]

    try:
        client = _get_twitter_client()
    except ValueError as e:
        return {"error": str(e), "user_found": False, "tweets": []}

    name_parts = politician_name.strip().split()

    # Generate potential handles
    potential_handles = []
    if len(name_parts) >= 2:
        first_name = name_parts[0].lower()
        last_name = name_parts[-1].lower()
        potential_handles.extend([
            f"{first_name}{last_name}",
            f"{first_name}_{last_name}",
            f"{last_name}{first_name}",
            f"{first_name}{last_name}{city.lower().replace(' ', '')}",
        ])
    if len(name_parts) >= 1:
        potential_handles.append(name_parts[0].lower())

    verified_username = None
    user_id = None

    # Try to find verified account
    for handle in potential_handles:
        is_valid, sanitized = _validate_twitter_handle(handle)
        if not is_valid:
            continue
        try:
            user_result = client.get_user(username=sanitized)
            if user_result and user_result.data:
                verified_username = sanitized
                user_id = user_result.data.id
                logger.info(f"Found verified Twitter account: @{verified_username}")
                break
        except Exception:
            continue

    user_tweets: list[dict] = []
    user_found = False

    # Get tweets from verified user
    if verified_username and user_id:
        try:
            tweets_response = client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),
                tweet_fields=tweet_fields,
            )
            user_tweets = _extract_tweets_from_response(tweets_response)
            if user_tweets:
                user_found = True
        except Exception:
            pass

    # Fallback: search tweets from potential handles
    if not user_found:
        for handle in potential_handles:
            is_valid, sanitized = _validate_twitter_handle(handle)
            if not is_valid:
                continue
            try:
                search_query = f"from:{sanitized} {city}" if city else f"from:{sanitized}"
                tweets_response = client.search_recent_tweets(
                    query=search_query,
                    max_results=min(max(max_results, 10), 100),
                    tweet_fields=tweet_fields,
                )
                extracted = _extract_tweets_from_response(tweets_response)
                if extracted:
                    user_tweets.extend(extracted)
                    user_found = True
                    verified_username = sanitized
                    break
            except Exception:
                continue

    # Fallback with research context
    if not user_found and research_context:
        safe_context = _sanitize_search_context(research_context)
        for handle in potential_handles:
            is_valid, sanitized = _validate_twitter_handle(handle)
            if not is_valid:
                continue
            try:
                search_query = f"from:{sanitized} {city} {safe_context}"
                tweets_response = client.search_recent_tweets(
                    query=search_query,
                    max_results=min(max(max_results, 10), 100),
                    tweet_fields=tweet_fields,
                )
                extracted = _extract_tweets_from_response(tweets_response)
                if extracted:
                    user_tweets.extend(extracted)
                    user_found = True
                    verified_username = sanitized
                    break
            except Exception:
                continue

    # Last resort: general search
    if not user_found:
        try:
            general_query = f"{politician_name} {city} official"
            fallback_response = client.search_recent_tweets(
                query=general_query,
                max_results=min(max(max_results, 10), 100),
                tweet_fields=tweet_fields,
            )
            user_tweets = _extract_tweets_from_response(fallback_response)
            if user_tweets:
                user_found = True
        except Exception:
            pass

    return {
        "error": None,
        "user_found": user_found,
        "verified_username": verified_username,
        "politician_name": politician_name,
        "tweets": user_tweets[:max_results],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
