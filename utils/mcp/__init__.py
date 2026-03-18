"""MCP client utilities for connecting to external MCP servers."""

from utils.mcp.brave_client import (
    get_brave_session,
    load_goggles,
    SMITHERY_BRAVE_SEARCH_URL,
)
from utils.mcp.twitter_client import (
    get_twitter_session,
    get_twitter_credentials,
    search_tweets,
    get_user_tweets,
    get_user_by_username,
    search_user_and_tweets,
    validate_twitter_handle,
    sanitize_search_context,
    is_error_response,
    extract_tweet_results,
    SMITHERY_TWITTER_URL,
)

__all__ = [
    "get_brave_session",
    "load_goggles",
    "SMITHERY_BRAVE_SEARCH_URL",
    "get_twitter_session",
    "get_twitter_credentials",
    "search_tweets",
    "get_user_tweets",
    "get_user_by_username",
    "search_user_and_tweets",
    "validate_twitter_handle",
    "sanitize_search_context",
    "is_error_response",
    "extract_tweet_results",
    "SMITHERY_TWITTER_URL",
]
