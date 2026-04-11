"""Context compression using LLMLingua-2 for LLM input token budget management.

LLMLingua-2 uses a BERT-based token-classification model to score each token's
informativeness and discard the least-informative ones. This preserves semantic
quality at high compression ratios — unlike simple truncation.

No API key is required. The model runs fully locally via HuggingFace transformers;
weights are downloaded from HuggingFace Hub on first use and cached locally.
"""

import logging
from functools import lru_cache

from config.constants import COMPRESSION_RATE, MIN_CHARS_TO_COMPRESS
from config.system_prompts import compression_instruction

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_compressor():
    """Load and cache the LLMLingua-2 model (runs once per process)."""
    from llmlingua import PromptCompressor  

    logger.info("Loading LLMLingua-2 model (first call only)…")
    compressor = PromptCompressor(
        model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        use_llmlingua2=True,
        device_map="cpu",
    )
    logger.info("LLMLingua-2 model ready.")
    return compressor


def compress_text(text: str, rate: float = COMPRESSION_RATE) -> str:
    """Compress *text* using LLMLingua-2, retaining the most informative tokens.

    Args:
        text: Raw content string to compress.
        rate: Fraction of tokens to keep (e.g. 0.5 = 50% retained).

    Returns:
        Compressed string with semantically important tokens preserved.
    """
    if len(text) < MIN_CHARS_TO_COMPRESS:
        return text

    compressor = _get_compressor()
    result = compressor.compress_prompt(
        text,
        rate=rate,
        instruction=compression_instruction,
        force_tokens=["\n", ".", "!", "?", ","],
        drop_consecutive=True,
    )
    compressed: str = result["compressed_prompt"]
    logger.info(
        "LLMLingua-2: %d → %d chars (%.0f%% retained)",
        len(text),
        len(compressed),
        100 * len(compressed) / max(len(text), 1),
    )
    return compressed

