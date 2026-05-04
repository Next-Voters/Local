"""Context compression via blended self-information token pruning.

Delegates to the CompactPrompt-based pruner for intelligent token-level
compression.  Falls back to head truncation if the pruner fails.
"""

import logging
from typing import Optional

from config.constants import COMPRESSION_RATE, MIN_CHARS_TO_COMPRESS

logger = logging.getLogger(__name__)


def compress_text(
    text: str,
    rate: float = COMPRESSION_RATE,
    query: Optional[str] = None,
) -> str:
    """Compress *text* by pruning low-information tokens.

    Uses blended self-information scoring (static + dynamic) with
    SpaCy phrase grouping.  Falls back to head truncation on any failure.

    Args:
        text: Raw content to compress.
        rate: Target retention rate (``0.0`` = drop everything, ``1.0`` = keep all).
        query: Pipeline topic — boosts preservation of topic-relevant tokens.

    Returns:
        The compressed text.
    """
    if not text or len(text) < MIN_CHARS_TO_COMPRESS:
        return text

    try:
        from utils.content.pruner import prune_text

        return prune_text(text, rate=rate, query=query)
    except Exception as exc:
        logger.warning("Pruner failed, falling back to head truncation: %s", exc)
        target_chars = max(MIN_CHARS_TO_COMPRESS, int(len(text) * rate))
        return text[:target_chars]
