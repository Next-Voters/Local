"""Static self-information scoring via pre-computed word frequencies.

Uses the ``wordfreq`` library to look up corpus-derived unigram frequencies
and convert them to self-information in bits:  I(t) = -log2(freq(t)).

Tokens not found in the corpus (OOV) receive a conservatively high score
so they are preserved rather than pruned.
"""

import math

from wordfreq import word_frequency

from config.constants import STATIC_OOV_SCORE


def score_token(token: str) -> float:
    """Return static self-information for *token* in bits.

    Whitespace-only tokens score ``0.0`` (no information content).
    OOV tokens score ``STATIC_OOV_SCORE`` (conservatively preserved).
    """
    word = token.strip().lower()
    if not word:
        return 0.0
    freq = word_frequency(word, "en")
    if freq == 0:
        return STATIC_OOV_SCORE
    return -math.log2(freq)


def score_tokens(tokens: list[str]) -> list[float]:
    """Return ``I_static`` for each token.  Pure lookup, O(n), thread-safe."""
    return [score_token(t) for t in tokens]
