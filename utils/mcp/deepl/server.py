"""DeepL MCP server — runs as a standalone stdio subprocess.

This file is NOT imported by app code. It is launched by client.py as a
subprocess. Provides a FastMCP tool wrapping the DeepL Python SDK for
text translation (Spanish and French only).

Usage: python -m utils.mcp.deepl.server
"""

import os

import deepl
from fastmcp import FastMCP

mcp = FastMCP("DeepL")

SUPPORTED_TARGET_LANGS = {"ES", "FR"}


def _get_translator() -> deepl.Translator:
    """Create a DeepL Translator instance from environment."""
    return deepl.Translator(os.environ.get("DEEPL_API_KEY", ""))


@mcp.tool
def translate_text(text: str, target_lang: str) -> dict:
    """Translate text to a target language using DeepL.

    Only Spanish (ES) and French (FR) are supported as target languages.

    Args:
        text: The text to translate.
        target_lang: Target language code — must be "ES" or "FR".

    Returns:
        Dict with translated_text and detected_source_lang.
    """
    target_lang = target_lang.upper()
    if target_lang not in SUPPORTED_TARGET_LANGS:
        return {
            "error": f"Unsupported target language: {target_lang}. "
            f"Supported: {', '.join(sorted(SUPPORTED_TARGET_LANGS))}"
        }

    translator = _get_translator()
    result = translator.translate_text(text, target_lang=target_lang)

    return {
        "translated_text": result.text,
        "detected_source_lang": result.detected_source_lang,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
