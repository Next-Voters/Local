"""JSON utility functions."""

from typing import Any


def extract_json(text: str) -> str:
    """Strip markdown code fences from LLM output before parsing."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
