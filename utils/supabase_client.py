"""
Supabase client utilities for Next Voters Local pipeline.

This module provides functions to query Supabase for:
- Supported cities (from supported_cities table)
- Supported topics (from supported_topics table)
- Supported languages (from supported_languages table)
- Subscribers with their city, topic, and language preferences (via subscription_topics junction table)
"""

import os
import logging
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)


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


def get_supported_cities_from_db() -> list[str]:
    """
    Query the supported_cities table from Supabase.

    Returns:
        List of city names sorted alphabetically

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying supported cities from Supabase...")
        response = (
            client.table("supported_cities").select("city").order("city").execute()
        )

        cities = [row["city"] for row in response.data]
        logger.info(f"Successfully retrieved {len(cities)} supported cities: {cities}")

        return cities

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query supported cities from Supabase: {e}")
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


def get_supported_languages() -> list[str]:
    """
    Query the supported_languages table from Supabase.

    Returns:
        List of language names sorted alphabetically

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying supported languages from Supabase...")
        response = (
            client.table("supported_languages")
            .select("language")
            .order("language")
            .execute()
        )

        languages = [row["language"] for row in response.data]
        logger.info(f"Successfully retrieved {len(languages)} supported languages: {languages}")

        return languages

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query supported languages from Supabase: {e}")
        raise


def get_all_subscribers_with_cities() -> list[dict[str, Any]]:
    """
    Query all subscribers with their city preferences from Supabase.

    Returns:
        List of dicts with keys: "contact" (email), "city" (city name), "preferred_language" (language or None)
        Example: [
            {"contact": "user@example.com", "city": "Toronto", "preferred_language": "English"},
            {"contact": "another@example.com", "city": "New York City", "preferred_language": None},
            ...
        ]

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying subscribers from Supabase...")
        response = client.table("subscriptions").select("contact, city, preferred_language").execute()

        subscribers = response.data if response.data else []
        logger.info(f"Successfully retrieved {len(subscribers)} subscribers")

        # Log breakdown by city
        cities_count = {}
        for subscriber in subscribers:
            city = subscriber.get("city")
            if city:
                cities_count[city] = cities_count.get(city, 0) + 1

        for city, count in sorted(cities_count.items()):
            logger.debug(f"  {city}: {count} subscriber(s)")

        return subscribers

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query subscribers from Supabase: {e}")
        raise


def get_all_subscribers_with_cities_and_topics() -> list[dict[str, Any]]:
    """
    Query all subscribers with their city and topic preferences from Supabase.

    Uses the subscription_topics junction table to resolve the many-to-many
    relationship between subscriptions and supported_topics.

    Returns:
        List of dicts with keys: "contact" (email), "city" (city name), "topics" (list of topic names), "preferred_language" (language or None)
        Example: [
            {"contact": "user@example.com", "city": "Toronto", "topics": ["immigration", "economy"], "preferred_language": "Spanish"},
            {"contact": "another@example.com", "city": "New York City", "topics": [], "preferred_language": None},
            ...
        ]

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.info("Querying subscribers with topics from Supabase...")
        response = (
            client.table("subscriptions")
            .select("contact, city, preferred_language, subscription_topics(supported_topics(topic_name))")
            .execute()
        )

        subscribers = []
        for row in (response.data or []):
            topic_entries = row.get("subscription_topics") or []
            topics = [
                entry["supported_topics"]["topic_name"]
                for entry in topic_entries
                if entry.get("supported_topics")
                and entry["supported_topics"].get("topic_name")
            ]
            subscribers.append({
                "contact": row.get("contact"),
                "city": row.get("city"),
                "topics": topics,
                "preferred_language": row.get("preferred_language"),
            })

        logger.info(f"Successfully retrieved {len(subscribers)} subscribers with topics")

        # Log breakdown by city
        cities_count: dict[str, int] = {}
        for subscriber in subscribers:
            city = subscriber.get("city")
            if city:
                cities_count[city] = cities_count.get(city, 0) + 1
        for city, count in sorted(cities_count.items()):
            logger.debug(f"  {city}: {count} subscriber(s)")

        # Log breakdown by topic
        topic_counts: dict[str, int] = {}
        for subscriber in subscribers:
            for topic in subscriber["topics"]:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for topic, count in sorted(topic_counts.items()):
            logger.debug(f"  {topic}: {count} subscriber(s)")

        return subscribers

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query subscribers with topics from Supabase: {e}")
        raise


def get_subscriber_referral_code(email: str) -> str | None:
    """Read the referral_code for a subscriber from the subscriptions table.

    Args:
        email: Subscriber's email address (contact column).

    Returns:
        The referral code string, or None if not set.

    Raises:
        ValueError: If Supabase credentials are missing.
        Exception: If the database query fails.
    """
    try:
        client = get_supabase_client()

        response = (
            client.table("subscriptions")
            .select("referral_code")
            .eq("contact", email)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0].get("referral_code")
        return None

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to get referral code for {email}: {e}")
        raise


def set_subscriber_referral_code(email: str, code: str) -> None:
    """Update the referral_code on a subscriber's subscription record.

    Args:
        email: Subscriber's email address (contact column).
        code: Referral code to set.

    Raises:
        ValueError: If Supabase credentials are missing.
        Exception: If the database update fails.
    """
    try:
        client = get_supabase_client()

        client.table("subscriptions").update(
            {"referral_code": code}
        ).eq("contact", email).execute()

        logger.debug(f"Set referral code for {email}: {code}")

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to set referral code for {email}: {e}")
        raise


def get_subscribers_for_city(city: str) -> list[str]:
    """
    Query subscribers for a specific city.

    Args:
        city: City name to filter by

    Returns:
        List of email addresses for subscribers in that city

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.debug(f"Querying subscribers for city: {city}")
        response = (
            client.table("subscriptions").select("contact").eq("city", city).execute()
        )

        emails = [row["contact"] for row in response.data]
        logger.debug(f"Found {len(emails)} subscriber(s) for {city}")

        return emails

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query subscribers for city {city}: {e}")
        raise


def get_subscribers_for_topic(topic: str) -> list[str]:
    """
    Query subscribers for a specific topic via the subscription_topics junction table.

    Args:
        topic: Topic name to filter by (e.g., "immigration", "civil rights", "economy")

    Returns:
        List of email addresses for subscribers with that topic preference

    Raises:
        ValueError: If Supabase credentials are missing
        Exception: If the database query fails
    """
    try:
        client = get_supabase_client()

        logger.debug(f"Querying subscribers for topic: {topic}")
        response = (
            client.table("subscription_topics")
            .select("subscription_id, supported_topics!inner(topic_name)")
            .eq("supported_topics.topic_name", topic)
            .execute()
        )

        emails = [row["subscription_id"] for row in response.data]
        logger.debug(f"Found {len(emails)} subscriber(s) for topic {topic}")

        return emails

    except ValueError as e:
        logger.error(f"Supabase configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to query subscribers for topic {topic}: {e}")
        raise
