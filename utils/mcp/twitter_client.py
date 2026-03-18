"""Smithery Twitter MCP client using official mcp Python SDK.

This module provides a clean connection to the Smithery-hosted Twitter MCP server
using the official Anthropic MCP Python SDK.

Usage:
    async with get_twitter_session() as session:
        result = await session.call_tool("TWITTER_SEARCH_TWEETS", {...})

Prerequisites:
    - Twitter Developer Account (free): https://developer.twitter.com/
    - API Key and Bearer Token from Twitter Developer Portal
"""

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from utils.mcp._shared import parse_mcp_result

logger = logging.getLogger(__name__)

SMITHERY_TWITTER_URL = "https://server.smithery.ai/@twitter/mcp"

SESSION_TIMEOUT = 30

TWITTER_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,15}$")

SAFE_CONTEXT_REGEX = re.compile(r"[^\w\s\-.,!?']")


def validate_twitter_handle(handle: str) -> tuple[bool, str]:
    """Validate a Twitter handle for safe use in queries.

    Args:
        handle: The Twitter handle to validate.

    Returns:
        Tuple of (is_valid, sanitized_handle).
    """
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


def sanitize_search_context(context: str, max_length: int = 100) -> str:
    """Sanitize research context for safe use in Twitter search queries.

    Removes newlines and special characters that could inject Twitter operators.

    Args:
        context: The raw context string.
        max_length: Maximum length of sanitized context.

    Returns:
        Sanitized string safe for search queries.
    """
    if not context:
        return ""

    sanitized = context.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    sanitized = re.sub(r"\s+", " ", sanitized)

    sanitized = SAFE_CONTEXT_REGEX.sub("", sanitized)

    sanitized = sanitized.strip()[:max_length]

    return sanitized


def get_twitter_credentials() -> dict[str, str]:
    """Get Twitter credentials from environment.

    Returns:
        Dict with API key and Bearer token.

    Raises:
        ValueError: If required credentials are missing.
    """
    api_key = os.getenv("TWITTER_API_KEY")
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

    if not api_key:
        raise ValueError(
            "TWITTER_API_KEY not set in environment. "
            "Get your API key at https://developer.twitter.com/"
        )
    if not bearer_token:
        raise ValueError(
            "TWITTER_BEARER_TOKEN not set in environment. "
            "Get your bearer token at https://developer.twitter.com/"
        )

    return {
        "api_key": api_key,
        "bearer_token": bearer_token,
    }


@asynccontextmanager
async def get_twitter_session():
    """Get MCP session connected to Smithery-hosted Twitter.

    Creates a fresh session each time - no global state.
    Session is properly cleaned up on exit.

    Yields:
        ClientSession: MCP session for calling Twitter tools
    """
    credentials = get_twitter_credentials()

    async with streamable_http_client(
        SMITHERY_TWITTER_URL,
        headers={
            "Authorization": f"Bearer {credentials['bearer_token']}",
            "X-API-Key": credentials["api_key"],
        },
        timeout=SESSION_TIMEOUT,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def is_error_response(response: dict[str, Any]) -> tuple[bool, str]:
    """Check if MCP response contains an error.

    Args:
        response: Parsed response from MCP.

    Returns:
        Tuple of (is_error, error_message).
    """
    if not isinstance(response, dict):
        return False, ""

    if "error" in response:
        return True, response.get("error", "Unknown error")

    if "errors" in response:
        errors = response.get("errors", [])
        if errors and isinstance(errors, list):
            return True, str(errors[0])

    return False, ""


async def search_tweets(
    query: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Search for tweets using the Twitter MCP server.

    Args:
        query: The search query (supports Twitter operators like 'from:username').
        max_results: Maximum number of results (1-100).

    Returns:
        Dict with search results or error dict.
    """
    async with get_twitter_session() as session:
        result = await session.call_tool(
            "TWITTER_SEARCH_TWEETS",
            {
                "query": query,
                "max_results": min(max_results, 100),
            },
        )

        return parse_mcp_result(result)


async def get_user_tweets(
    username: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Get recent tweets from a specific Twitter user.

    Args:
        username: The Twitter handle (without @).
        max_results: Maximum number of results (1-100).

    Returns:
        Dict with user's recent tweets or error dict.
    """
    is_valid, sanitized = validate_twitter_handle(username)
    if not is_valid:
        return {"error": f"Invalid Twitter handle: {username}", "data": []}

    query = f"from:{sanitized}"

    return await search_tweets(query=query, max_results=max_results)


async def get_user_by_username(
    username: str,
) -> dict[str, Any]:
    """Get Twitter user information by username.

    Args:
        username: The Twitter handle (without @).

    Returns:
        Dict with user profile information or error dict.
    """
    is_valid, sanitized = validate_twitter_handle(username)
    if not is_valid:
        return {"error": f"Invalid Twitter handle: {username}", "data": None}

    async with get_twitter_session() as session:
        result = await session.call_tool(
            "TWITTER_GET_USER_BY_USERNAME",
            {
                "username": sanitized,
            },
        )

        return parse_mcp_result(result)


async def search_user_and_tweets(
    politician_name: str,
    city: str = "",
    research_context: str = "",
    max_results: int = 10,
) -> dict[str, Any]:
    """Look up a politician's Twitter account and search their tweets.

    First attempts to find the politician's Twitter account by trying common
    handle formats, then retrieves their tweets filtered by city and context.

    Args:
        politician_name: The full name of the politician to search for.
        city: The city to filter tweets by.
        research_context: Additional context for filtering tweets.
        max_results: Maximum number of tweets to retrieve.

    Returns:
        Dict with user info, tweets, and any errors.
    """
    if not city:
        city = ""

    if not politician_name or not politician_name.strip():
        return {
            "error": "Politician name is required",
            "user_found": False,
            "tweets": [],
        }
    name_parts = politician_name.strip().split()

    potential_handles = []
    if len(name_parts) >= 2:
        first_name = name_parts[0].lower()
        last_name = name_parts[-1].lower()
        potential_handles.append(f"{first_name}{last_name}")
        potential_handles.append(f"{first_name}_{last_name}")
        potential_handles.append(f"{last_name}{first_name}")
        potential_handles.append(
            f"{first_name}{last_name}{city.lower().replace(' ', '')}"
        )

    if len(name_parts) >= 1:
        potential_handles.append(name_parts[0].lower())

    verified_username = None

    for handle in potential_handles:
        is_valid, sanitized = validate_twitter_handle(handle)
        if not is_valid:
            continue

        user_result = await get_user_by_username(username=sanitized)

        is_err, _ = is_error_response(user_result)
        if not is_err:
            if extract_user_info(user_result):
                verified_username = sanitized
                logger.info(
                    f"Found verified Twitter account: @{verified_username} for {politician_name}"
                )
                break

    user_tweets = []
    user_found = False

    if verified_username:
        tweets_result = await get_user_tweets(
            username=verified_username, max_results=max_results
        )

        is_err, _ = is_error_response(tweets_result)
        if not is_err:
            user_tweets = extract_tweet_results(tweets_result)
            if user_tweets:
                user_found = True

    if not user_found:
        for handle in potential_handles:
            is_valid, sanitized = validate_twitter_handle(handle)
            if not is_valid:
                continue

            search_query = f"from:{sanitized} {city}"
            tweets_result = await search_tweets(
                query=search_query, max_results=max_results
            )

            is_err, _ = is_error_response(tweets_result)
            if not is_err:
                extracted = extract_tweet_results(tweets_result)
                if extracted:
                    user_tweets.extend(extracted)
                    user_found = True
                    verified_username = sanitized
                    break

    if not user_found and research_context:
        safe_context = sanitize_search_context(research_context)
        for handle in potential_handles:
            is_valid, sanitized = validate_twitter_handle(handle)
            if not is_valid:
                continue

            search_query = f"from:{sanitized} {city} {safe_context}"
            tweets_result = await search_tweets(
                query=search_query, max_results=max_results
            )

            is_err, _ = is_error_response(tweets_result)
            if not is_err:
                extracted = extract_tweet_results(tweets_result)
                if extracted:
                    user_tweets.extend(extracted)
                    user_found = True
                    verified_username = sanitized
                    break

    if not user_found:
        general_query = f"{politician_name} {city} official"
        fallback_result = await search_tweets(
            query=general_query, max_results=max_results
        )

        is_err, _ = is_error_response(fallback_result)
        if not is_err:
            user_tweets = extract_tweet_results(fallback_result)
            if user_tweets:
                user_found = True

    return {
        "error": None,
        "user_found": user_found,
        "verified_username": verified_username,
        "politician_name": politician_name,
        "tweets": user_tweets[:max_results],
    }


def extract_tweet_results(raw_results: dict) -> list[dict]:
    """Extract relevant fields from Twitter search results.

    Args:
        raw_results: Raw response from Twitter MCP.

    Returns:
        List of dicts with tweet info.
    """
    results = []

    if not isinstance(raw_results, dict):
        logger.warning(f"Unexpected result type: {type(raw_results)}")
        return results

    is_err, _ = is_error_response(raw_results)
    if is_err:
        logger.warning(f"Error response received: {raw_results}")
        return results

    data = raw_results.get("data")

    if data is None:
        logger.info("No 'data' key in response")
        return results

    if not isinstance(data, list):
        logger.warning(f"Unexpected 'data' type: {type(data)}")
        return results

    for tweet in data:
        if not isinstance(tweet, dict):
            continue

        results.append(
            {
                "id": tweet.get("id"),
                "text": tweet.get("text"),
                "author_id": tweet.get("author_id"),
                "created_at": tweet.get("created_at"),
                "public_metrics": tweet.get("public_metrics", {}),
            }
        )

    return results


def extract_user_info(raw_results: dict) -> dict[str, Any]:
    """Extract user info from Twitter user lookup response.

    Args:
        raw_results: Raw response from Twitter MCP user lookup.

    Returns:
        Dict with user info or empty dict if not found.
    """
    if not isinstance(raw_results, dict):
        return {}

    is_err, _ = is_error_response(raw_results)
    if is_err:
        return {}

    data = raw_results.get("data")

    if not isinstance(data, dict):
        return {}

    return {
        "id": data.get("id"),
        "username": data.get("username"),
        "name": data.get("name"),
        "public_metrics": data.get("public_metrics", {}),
    }
