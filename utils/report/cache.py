"""In-memory cache for city+topic pipeline reports and their translations.

This module provides a module-level cache for storing and retrieving
reports keyed by (city, topic). Translated versions of reports are stored
in a parallel cache keyed by (city, topic, lang_code). The module itself
acts as a singleton — import it from anywhere to access the same cached data.

Used by the container runner to store reports as pipelines complete,
and by the email dispatcher to retrieve them for delivery.
"""

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, dict[str, str]] = {}
_translations: dict[str, dict[str, dict[str, str]]] = {}  # {city: {topic: {lang: report}}}


def store(city: str, topic: str, report: str) -> None:
    """Store a report for a city+topic pair. Skips empty/falsy reports."""
    if report:
        if city not in _cache:
            _cache[city] = {}
        _cache[city][topic] = report


def get(city: str, topic: str) -> str | None:
    """Retrieve a cached report by city and topic."""
    return _cache.get(city, {}).get(topic)


def get_for_city(city: str) -> dict[str, str]:
    """Return a copy of all topic reports for a specific city."""
    return dict(_cache.get(city, {}))


def get_all() -> dict[str, dict[str, str]]:
    """Return a deep copy of all cached reports."""
    return copy.deepcopy(_cache)


def build_from_results(results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Populate the cache from pipeline results and return all cached reports.

    Clears existing cache, then stores each (city, topic) report if non-empty.

    Args:
        results: Pipeline results indexed by (city, topic) tuple.

    Returns:
        Deep copy of all cached reports.
    """
    clear()
    for (city, topic), result in results.items():
        store(city, topic, result.get("markdown_report", ""))

    total = sum(len(topics) for topics in _cache.values())
    logger.info(f"Cached {total} reports across {len(_cache)} cities")
    return get_all()


def store_translation(city: str, topic: str, lang: str, report: str) -> None:
    """Store a translated report for a city+topic+language triple. Skips empty/falsy reports."""
    if report:
        _translations.setdefault(city, {}).setdefault(topic, {})[lang] = report


def store_all_translations(translations: dict[str, dict[str, dict[str, str]]]) -> None:
    """Bulk-store translations from translate_all_reports() output.

    Args:
        translations: Nested dict {city: {topic: {lang_code: translated_report}}}.
    """
    for city, topics in translations.items():
        for topic, langs in topics.items():
            for lang, report in langs.items():
                store_translation(city, topic, lang, report)


def get_translation(city: str, topic: str, lang: str) -> str | None:
    """Retrieve a single translated report by city, topic, and language code."""
    return _translations.get(city, {}).get(topic, {}).get(lang)


def get_all_translations() -> dict[str, dict[str, dict[str, str]]]:
    """Return a deep copy of all cached translations."""
    return copy.deepcopy(_translations)


def clear() -> None:
    """Clear all cached reports and translations."""
    _cache.clear()
    _translations.clear()
