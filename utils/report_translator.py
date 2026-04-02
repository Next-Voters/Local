"""Translate cached pipeline reports to Spanish and French via DeepL MCP.

This module provides a sync entry point that translates all reports in the
report cache to the supported target languages. Translation is optional —
if DEEPL_API_KEY is not set, translation is skipped gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from utils.async_runner import run_async

logger = logging.getLogger(__name__)

TARGET_LANGUAGES = ("ES", "FR")


async def _translate_single(
    text: str, target_lang: str
) -> dict[str, Any]:
    """Translate a single text string via the DeepL MCP client."""
    from utils.mcp.deepl.client import translate_text

    return await translate_text(text, target_lang)


async def _translate_all_reports_async(
    reports: dict[str, dict[str, str]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Translate all reports to all target languages concurrently.

    Args:
        reports: Nested dict of {city: {topic: markdown_report}}.

    Returns:
        Nested dict of {city: {topic: {lang_code: translated_report}}}.
    """
    from utils.mcp.deepl.client import managed_deepl_session

    translations: dict[str, dict[str, dict[str, str]]] = {}

    # Collect all (city, topic, lang, text) translation jobs
    jobs: list[tuple[str, str, str, str]] = []
    for city, topics in reports.items():
        for topic, text in topics.items():
            if not text:
                continue
            for lang in TARGET_LANGUAGES:
                jobs.append((city, topic, lang, text))

    if not jobs:
        return translations

    logger.info(f"Translating {len(jobs)} report segments ({len(jobs) // len(TARGET_LANGUAGES)} reports x {len(TARGET_LANGUAGES)} languages)")

    async with managed_deepl_session():
        tasks = [
            _translate_single(text, lang)
            for _, _, lang, text in jobs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for (city, topic, lang, _), result in zip(jobs, results):
        if isinstance(result, Exception):
            logger.warning(f"Translation failed for {city}/{topic}/{lang}: {result}")
            continue

        translated_text = result.get("translated_text", "")
        if result.get("error"):
            logger.warning(f"Translation error for {city}/{topic}/{lang}: {result['error']}")
            continue

        if not translated_text:
            continue

        translations.setdefault(city, {}).setdefault(topic, {})[lang] = translated_text

    total = sum(
        len(langs)
        for topics in translations.values()
        for langs in topics.values()
    )
    logger.info(f"Successfully translated {total}/{len(jobs)} report segments")

    return translations


def translate_all_reports(
    reports: dict[str, dict[str, str]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Translate all cached reports to Spanish and French.

    Sync entry point that wraps the async implementation.
    Returns empty dict if DEEPL_API_KEY is not set.

    Args:
        reports: Nested dict of {city: {topic: markdown_report}}.

    Returns:
        Nested dict of {city: {topic: {lang_code: translated_report}}}.
    """
    if not os.getenv("DEEPL_API_KEY"):
        logger.info("DEEPL_API_KEY not set; skipping report translation")
        return {}

    if not reports:
        return {}

    return run_async(lambda: _translate_all_reports_async(reports))
