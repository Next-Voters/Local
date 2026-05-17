"""
Supabase client utilities for Next Voters Local pipeline.

This module provides functions to query Supabase for:
- Supported regions (from regions table)
- Supported topics (from supported_topics table)
"""

import os

from dotenv import load_dotenv
from supabase import create_client, Client

from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


def get_supabase_client() -> Client:
    """
    Create and return a Supabase client from environment variables.

    Returns:
        Supabase Client object

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY environment variables are not set
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url:
        raise ValueError(
            "SUPABASE_URL environment variable is not set. "
            "Please set it to your Supabase project URL (e.g., https://project.supabase.co)"
        )

    if not supabase_key:
        raise ValueError(
            "SUPABASE_KEY environment variable is not set. "
            "Please set it to your Supabase API key."
        )

    logger.debug(f"Connecting to Supabase at {supabase_url}")
    return create_client(supabase_url, supabase_key)


def get_supported_regions_from_db() -> list[str]:
    """
    Query the regions table from Supabase.

    Returns:
        List of region names sorted alphabetically

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying supported regions from Supabase...")
        response = (
            client.table("regions").select("region").order("region").execute()
        )

        regions = [row["region"] for row in response.data]
        logger.info(f"Successfully retrieved {len(regions)} supported regions: {regions}")

        return regions

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query supported regions from Supabase: {e}")
        raise


def get_supported_topics() -> list[str]:
    """
    Query the supported_topics table from Supabase.

    Returns:
        List of topic names sorted alphabetically

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying supported topics from Supabase...")
        response = (
            client.table("supported_topics")
            .select("topic_name")
            .order("topic_name")
            .execute()
        )

        topics = [row["topic_name"] for row in response.data]
        logger.info(f"Successfully retrieved {len(topics)} supported topics: {topics}")

        return topics

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query supported topics from Supabase: {e}")
        raise


def get_region_details(region: str) -> dict | None:
    """Look up city-specific legislative context from the region_details table.

    Returns a single row dict with governing_body, official_website,
    legislative_portal, legistar_domain, legislative_terms, etc.,
    or None if the region has no entry.
    """
    client = get_supabase_client()
    response = (
        client.table("region_details")
        .select("*")
        .eq("region", region)
        .maybe_single()
        .execute()
    )
    return response.data
