"""CompactPrompt-style blended self-information token pruning.

Orchestrates static scoring (``wordfreq``), dynamic scoring (Together AI
GPT-OSS-20B logprobs), and SpaCy phrase grouping to prune low-value tokens
from legislative web content while preserving high-information tokens
regardless of their position in the document.

Reference: *CompactPrompt* (arXiv:2510.18043)
"""

from typing import Optional

from config.constants import (
    BLEND_DELTA_THRESHOLD,
    COMPRESSION_RATE,
    MIN_CHARS_TO_COMPRESS,
    QUERY_BOOST_FACTOR,
)
from utils.content.dynamic_scorer import DynamicScoringError, get_dynamic_scores
from utils.content.phrase_grouper import get_phrase_groups
from utils.content.static_scorer import score_tokens as static_score_tokens
from utils.logger import get_logger

logger = get_logger(__name__)


def prune_text(
    text: str,
    rate: float = COMPRESSION_RATE,
    query: Optional[str] = None,
) -> str:
    """Prune low-information tokens using blended self-information scoring.

    Drop-in replacement for the former ``compress_text`` head-truncation
    function.  Same signature, same return type.

    Args:
        text: Raw content to prune.
        rate: Target retention rate (``0.0``–``1.0``).
        query: Pipeline topic — tokens matching the query receive a
            score boost so topic-relevant content is preserved.

    Returns:
        Pruned text with low-information tokens removed.
    """
    if not text or len(text) < MIN_CHARS_TO_COMPRESS:
        return text

    # ------------------------------------------------------------------
    # 1. Dynamic scoring  →  canonical token list + I_dynamic per token
    # ------------------------------------------------------------------
    dynamic_scores: Optional[list[tuple[str, float]]] = None
    try:
        dynamic_scores = get_dynamic_scores(text)
    except DynamicScoringError as exc:
        logger.warning("Dynamic scoring unavailable, using static-only: %s", exc)

    # Track whether we have BPE tokens from Together AI (controls
    # phrase grouping eligibility and text reassembly strategy).
    has_bpe_tokens = False

    if dynamic_scores is not None:
        tokens = [tok for tok, _ in dynamic_scores]
        i_dynamic = [score for _, score in dynamic_scores]
        has_bpe_tokens = True
    else:
        # Fallback: split on whitespace so static scoring can still work.
        # Phrase grouping is skipped in this path because whitespace-split
        # tokens cannot be mapped back to character offsets reliably.
        tokens = text.split()
        i_dynamic = None

    if not tokens:
        return text

    # ------------------------------------------------------------------
    # 2. Static scoring  →  I_static per token (via wordfreq)
    # ------------------------------------------------------------------
    i_static = static_score_tokens(tokens)

    # ------------------------------------------------------------------
    # 3. Blend scores
    # ------------------------------------------------------------------
    blended = _blend_scores(i_static, i_dynamic)

    # ------------------------------------------------------------------
    # 4. Query boost
    # ------------------------------------------------------------------
    if query:
        query_terms = {w.lower() for w in query.split()}
        for i, tok in enumerate(tokens):
            tok_lower = tok.strip().lower()
            if tok_lower and any(qt in tok_lower for qt in query_terms):
                blended[i] *= QUERY_BOOST_FACTOR

    # ------------------------------------------------------------------
    # 5. Phrase grouping (SpaCy)
    # ------------------------------------------------------------------
    # BPE token concatenation may differ from the original text (whitespace
    # normalisation, unicode, BOS markers).  Pass the reconstructed text to
    # SpaCy so that character offsets align with _token_char_ranges().
    # In the whitespace-split fallback path, skip phrase grouping entirely
    # because split tokens cannot be mapped back to character offsets.
    if has_bpe_tokens:
        reconstructed = "".join(tokens)
        phrase_groups = get_phrase_groups(reconstructed, tokens)
    else:
        phrase_groups = []
    token_to_group: dict[int, int] = {}
    for gid, group in enumerate(phrase_groups):
        for idx in group:
            token_to_group[idx] = gid

    # ------------------------------------------------------------------
    # 6. Threshold
    # ------------------------------------------------------------------
    target_keep = max(1, int(len(blended) * rate))
    threshold = _compute_threshold(blended, target_keep)

    # ------------------------------------------------------------------
    # 7. Prune with phrase constraint
    # ------------------------------------------------------------------
    keep = [False] * len(tokens)
    # Pre-compute phrase-level mean scores.
    group_means: dict[int, float] = {}
    for gid, group in enumerate(phrase_groups):
        group_means[gid] = sum(blended[idx] for idx in group) / len(group)

    for i in range(len(tokens)):
        if blended[i] >= threshold:
            keep[i] = True
        else:
            gid = token_to_group.get(i)
            if gid is not None and group_means[gid] >= threshold:
                keep[i] = True

    # ------------------------------------------------------------------
    # 8. Reassemble
    # ------------------------------------------------------------------
    if i_dynamic is not None:
        # BPE tokens — concatenate directly (they encode their own spacing).
        pruned = "".join(tok for tok, k in zip(tokens, keep) if k)
    else:
        # Whitespace-split fallback — rejoin with spaces.
        pruned = " ".join(tok for tok, k in zip(tokens, keep) if k)

    kept_count = sum(keep)
    logger.info(
        "Pruned: %d → %d tokens (%.0f%% retained)",
        len(tokens),
        kept_count,
        100 * kept_count / max(len(tokens), 1),
    )

    # Safety floor: if pruning eliminated (nearly) everything, return the
    # original text so the downstream pipeline never receives empty content.
    if not pruned.strip():
        logger.warning("Pruning produced empty output; returning original text.")
        return text

    return pruned


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _blend_scores(
    i_static: list[float],
    i_dynamic: Optional[list[float]],
) -> list[float]:
    """Blend static and dynamic self-information per the CompactPrompt formula.

    When dynamic scores are unavailable, static scores are returned as-is.
    """
    if i_dynamic is None:
        return list(i_static)

    blended: list[float] = []
    for s_stat, s_dyn in zip(i_static, i_dynamic):
        if s_stat == 0:
            blended.append(s_dyn)
        else:
            delta = abs(s_dyn - s_stat) / s_stat
            if delta <= BLEND_DELTA_THRESHOLD:
                blended.append((s_stat + s_dyn) / 2.0)
            else:
                blended.append(s_dyn)
    return blended


def _compute_threshold(scores: list[float], target_keep: int) -> float:
    """Return the score threshold that retains *target_keep* tokens."""
    if target_keep >= len(scores):
        return 0.0
    sorted_scores = sorted(scores)
    cutoff_index = len(sorted_scores) - target_keep
    cutoff_index = max(0, min(cutoff_index, len(sorted_scores) - 1))
    return sorted_scores[cutoff_index]
