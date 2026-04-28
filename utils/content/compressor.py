"""Context compression via head truncation.

Retains the first N characters of each text block based on the configured
compression rate. This is a simple, memory-safe approach that avoids loading
a local scorer model (~1 GB) which causes OOM in memory-constrained containers.
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
    """Compress *text* by retaining the first ``rate * len(text)`` characters.

    Args:
        text: Raw content to compress.
        rate: Target retention rate (``0.0`` = drop everything, ``1.0`` = keep all).
        query: Unused. Reserved for future query-aware ranking.

    Returns:
        The truncated text.
    """
    if not text or len(text) < MIN_CHARS_TO_COMPRESS:
        return text

    target_chars = max(MIN_CHARS_TO_COMPRESS, int(len(text) * rate))
    compressed = text[:target_chars]

    logger.info(
        "Compressed: %d → %d chars (%.0f%% retained)",
        len(text),
        len(compressed),
        100 * len(compressed) / max(len(text), 1),
    )
    return compressed
