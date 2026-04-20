"""
Per-subscriber content assembly for the email dispatcher.

Two concerns live here:

1. Selecting which topic reports — in which language — go to each subscriber,
   given their topic preferences and the pool of city/topic reports and
   translations.
2. Persisting delivery failures to the local JSON log after a dispatch run.

Both are called from ``pipelines/node/email_dispatcher.py``. Keeping them
colocated here keeps the dispatcher itself focused on orchestration.
"""

import json
import os
import logging


logger = logging.getLogger(__name__)


def build_subscriber_topic_reports(
    subscriber_topics: list[str],
    city_reports: dict[str, str],
) -> list[tuple[str, str]]:
    """Build list of (topic_name, markdown) tuples from matching topic reports for a subscriber.

    Args:
        subscriber_topics: List of topic names the subscriber is interested in
        city_reports: Dict mapping topic name to markdown report for the subscriber's city

    Returns:
        List of (topic_name, markdown) tuples for matching topics
    """
    reports = []
    for topic in subscriber_topics:
        topic_report = city_reports.get(topic)
        if topic_report:
            reports.append((topic, topic_report))
    return reports


def build_translated_subscriber_topic_reports(
    subscriber_topics: list[str],
    city: str,
    lang_code: str,
    translations: dict[str, dict[str, dict[str, str]]],
) -> list[tuple[str, str]]:
    """Build list of (topic_name, translated_markdown) tuples for a subscriber's preferred language.

    Args:
        subscriber_topics: List of topic names the subscriber is interested in.
        city: The subscriber's city.
        lang_code: Target language code (e.g. "ES", "FR").
        translations: Nested dict {city: {topic: {lang: translated_markdown}}}.

    Returns:
        List of (topic_name, translated_markdown) tuples, or empty list if no translations available.
    """
    city_translations = translations.get(city, {})
    if not city_translations:
        return []

    reports = []
    for topic in subscriber_topics:
        translated = city_translations.get(topic, {}).get(lang_code, "")
        if translated:
            reports.append((topic, translated))
    return reports


def save_failures(failures: list[dict]):
    """Save email delivery failures to a JSON file.

    Args:
        failures: List of failure records
    """
    if not failures:
        return
    failures_path = os.path.join(os.path.dirname(__file__), "..", "email_failures.json")
    with open(failures_path, "w") as f:
        json.dump(failures, f, indent=2)
    logger.warning(f"Saved {len(failures)} email delivery failures to {failures_path}")
