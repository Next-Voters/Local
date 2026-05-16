"""Dependency-based phrase grouping via SpaCy.

Identifies syntactic units (noun chunks, named entities, compound phrases)
that should be pruned or preserved as a whole.  This prevents the pruner
from splitting phrases like "Ordinance 2024-157" or "City Council".
"""

from functools import lru_cache
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_nlp():
    """Load the SpaCy English model once (thread-safe via ``lru_cache``)."""
    import spacy  # noqa: local import to defer the heavy load

    nlp = spacy.load("en_core_web_sm")
    nlp.max_length = 200_000
    return nlp


def get_phrase_groups(
    text: str,
    token_strings: list[str],
) -> list[list[int]]:
    """Identify groups of token indices that form syntactic phrases.

    Uses SpaCy's dependency parser to find noun chunks, named entities,
    and compound phrases, then maps those character spans back to BPE
    token indices.

    Args:
        text: Original document text.
        token_strings: Ordered list of token strings from the tokeniser
            (Together AI echo response).

    Returns:
        List of groups, where each group is a list of token indices that
        must be pruned or kept together.  Returns an empty list on failure.
    """
    try:
        return _build_groups(text, token_strings)
    except Exception as exc:
        logger.warning("Phrase grouper failed, falling back to ungrouped: %s", exc)
        return []


def _build_groups(
    text: str,
    token_strings: list[str],
) -> list[list[int]]:
    """Core implementation — may raise on SpaCy errors."""
    nlp = _load_nlp()
    doc = nlp(text)

    # ------------------------------------------------------------------
    # 1. Collect character-level spans from SpaCy
    # ------------------------------------------------------------------
    char_spans: list[tuple[int, int]] = []

    # Noun chunks  ("City Council", "the proposed ordinance")
    for chunk in doc.noun_chunks:
        char_spans.append((chunk.start_char, chunk.end_char))

    # Named entities  ("January 15, 2024", "Bill 2024-157")
    for ent in doc.ents:
        char_spans.append((ent.start_char, ent.end_char))

    # Compound dependency chains  ("Ordinance" + "2024-157")
    for token in doc:
        if token.dep_ in ("compound", "nummod"):
            head = token.head
            start = min(token.idx, head.idx)
            end = max(
                token.idx + len(token.text),
                head.idx + len(head.text),
            )
            char_spans.append((start, end))

    if not char_spans:
        return []

    # ------------------------------------------------------------------
    # 2. Build a character-offset → token-index map
    # ------------------------------------------------------------------
    token_char_ranges = _token_char_ranges(token_strings)

    # ------------------------------------------------------------------
    # 3. Map each SpaCy span to overlapping token indices
    # ------------------------------------------------------------------
    raw_groups: list[set[int]] = []
    for span_start, span_end in char_spans:
        group: set[int] = set()
        for idx, (ts, te) in enumerate(token_char_ranges):
            if ts < span_end and te > span_start:  # overlap
                group.add(idx)
        if len(group) > 1:
            raw_groups.append(group)

    # ------------------------------------------------------------------
    # 4. Merge overlapping groups
    # ------------------------------------------------------------------
    merged = _merge_overlapping(raw_groups)
    return [sorted(g) for g in merged]


def _token_char_ranges(
    token_strings: list[str],
) -> list[tuple[int, int]]:
    """Map each token to its ``(start_char, end_char)`` in the original text.

    BPE tokens may include leading whitespace (e.g. ``" Ordinance"``).
    We reconstruct positions by walking the concatenated token sequence.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    for tok in token_strings:
        end = pos + len(tok)
        ranges.append((pos, end))
        pos = end
    return ranges


def _merge_overlapping(groups: list[set[int]]) -> list[set[int]]:
    """Union-find style merge of overlapping index sets."""
    if not groups:
        return []

    merged: list[set[int]] = [groups[0].copy()]
    for g in groups[1:]:
        found: Optional[int] = None
        for i, m in enumerate(merged):
            if m & g:
                if found is None:
                    m |= g
                    found = i
                else:
                    # This group bridges two existing merged sets — union them.
                    merged[found] |= m | g
                    merged[i] = set()  # mark for removal
        if found is None:
            merged.append(g.copy())

    return [m for m in merged if m]
