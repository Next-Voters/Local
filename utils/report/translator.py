"""Translate cached pipeline reports to Spanish and French via the DeepL SDK.

This module provides a synchronous, deterministic translation layer that
translates all reports in the report cache to the supported target languages.
Translation is optional — if DEEPL_API_KEY is not set, translation is skipped
gracefully.
"""

import logging
import os

import deepl
from dotenv import load_dotenv

from utils.concurrency import run_parallel

load_dotenv()

logger = logging.getLogger(__name__)

LANG_MAP = {"Spanish": "ES", "French": "FR"}
TARGET_LANGUAGES = tuple(LANG_MAP.values())


def _get_translator() -> deepl.Translator | None:
    """Create a DeepL Translator instance from the environment API key.

    Returns:
        Translator instance, or None if DEEPL_API_KEY is not set.
    """
    api_key = os.getenv("DEEPL_API_KEY")
    if not api_key:
        return None
    return deepl.Translator(api_key)


def translate_text(translator: deepl.Translator, text: str, target_lang: str) -> str:
    """Translate a single text string using the DeepL SDK.

    Args:
        translator: Initialized DeepL Translator instance.
        text: Source text to translate.
        target_lang: Target language code (e.g. "ES", "FR").

    Returns:
        Translated text string.
    """
    result = translator.translate_text(text, target_lang=target_lang)
    return result.text


def translate_all_reports(
    reports: dict[str, dict[str, str]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Translate all cached reports to Spanish and French.

    Args:
        reports: Nested dict of {city: {topic: markdown_report}}.

    Returns:
        Nested dict of {city: {topic: {lang_code: translated_report}}}.
        Returns empty dict if DEEPL_API_KEY is not set or reports is empty.
    """
    translator = _get_translator()
    if translator is None:
        logger.info("DEEPL_API_KEY not set; skipping report translation")
        return {}

    if not reports:
        return {}

    # Build the full (city, topic, lang, text) job list up front so we can
    # fan out with run_parallel. Each DeepL call is a blocking HTTP request,
    # so threads are the right concurrency primitive here.
    jobs: list[tuple[str, str, str, str]] = [
        (city, topic, lang, text)
        for city, topics in reports.items()
        for topic, text in topics.items()
        if text
        for lang in TARGET_LANGUAGES
    ]

    def _job(item: tuple[str, str, str, str]) -> str:
        _, _, lang, text = item
        return translate_text(translator, text, lang)

    results = run_parallel(_job, jobs)

    translations: dict[str, dict[str, dict[str, str]]] = {}
    successful = 0
    for res in results:
        city, topic, lang, _ = res.item
        if res.ok and res.value:
            translations.setdefault(city, {}).setdefault(topic, {})[lang] = res.value
            successful += 1
        else:
            logger.warning(
                "Translation failed for %s/%s/%s: %r", city, topic, lang, res.error
            )

    logger.info(f"Successfully translated {successful}/{len(jobs)} report segments")
    return translations