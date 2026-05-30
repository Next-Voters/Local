"""Dynamic self-information scoring via Together AI logprobs.

Sends document text to GPT-OSS-20B hosted on Together AI and extracts
per-token log-probabilities from the echo response.  Each token's dynamic
self-information is computed as  I_dyn(t) = -log_e(P(t|ctx)) / ln(2).
"""

import math
import os
import time

import httpx
from dotenv import load_dotenv

from config.constants import (
    STATIC_OOV_SCORE,
    TOGETHER_MAX_RETRIES,
    TOGETHER_MODEL,
    TOGETHER_TIMEOUT,
)
from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

_TOGETHER_API_URL = "https://api.together.xyz/v1/completions"
_LN2 = math.log(2)


class DynamicScoringError(Exception):
    """Raised when the Together AI scoring call fails after retries."""


def get_dynamic_scores(
    text: str,
) -> list[tuple[str, float]]:
    """Return ``(token_string, I_dynamic)`` pairs for every input token.

    Calls Together AI ``/v1/completions`` with ``echo=true`` and
    ``logprobs=5``.  The response's ``tokens`` list is used as the
    canonical tokenisation — no local tokeniser is needed.

    Args:
        text: The full document text to score.

    Returns:
        List of ``(token_string, dynamic_self_information_bits)`` tuples,
        one per input token, in document order.

    Raises:
        DynamicScoringError: When the API call fails after retries.
    """
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        raise DynamicScoringError("TOGETHER_API_KEY not set")

    # max_tokens must be >= 1 on some providers; the extra generated token
    # is stripped in _parse_response so it doesn't leak into the output.
    _GENERATED_TOKENS = 1

    payload = {
        "model": TOGETHER_MODEL,
        "prompt": text,
        "max_tokens": _GENERATED_TOKENS,
        "echo": True,
        "logprobs": 5,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(1 + TOGETHER_MAX_RETRIES):
        try:
            response = httpx.post(
                _TOGETHER_API_URL,
                json=payload,
                headers=headers,
                timeout=TOGETHER_TIMEOUT,
            )
            if response.status_code == 429:
                try:
                    retry_after = int(response.headers.get("Retry-After", 2))
                except (ValueError, TypeError):
                    retry_after = 2
                logger.warning(
                    "Together AI rate-limited (429). Retry after %ds.", retry_after
                )
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return _parse_response(response.json(), _GENERATED_TOKENS)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            logger.warning(
                "Together AI HTTP %s on attempt %d/%d: %s",
                exc.response.status_code,
                attempt + 1,
                1 + TOGETHER_MAX_RETRIES,
                exc,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc
            logger.warning(
                "Together AI connection error on attempt %d/%d: %s",
                attempt + 1,
                1 + TOGETHER_MAX_RETRIES,
                exc,
            )

        if attempt < TOGETHER_MAX_RETRIES:
            backoff = 2**attempt
            time.sleep(backoff)

    raise DynamicScoringError(
        f"Together AI failed after {1 + TOGETHER_MAX_RETRIES} attempts: {last_error}"
    )


def _parse_response(data: dict, generated_count: int = 1) -> list[tuple[str, float]]:
    """Extract ``(token, I_dynamic)`` pairs from the API response.

    With ``echo=True`` the response contains echoed prompt tokens followed
    by ``generated_count`` generated tokens.  The generated tail is stripped
    so only prompt tokens are returned.
    """
    try:
        choice = data["choices"][0]
        logprobs_obj = choice["logprobs"]
        tokens: list[str] = logprobs_obj["tokens"]
        token_logprobs: list[float | None] = logprobs_obj["token_logprobs"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DynamicScoringError(f"Unexpected response shape: {exc}") from exc

    # Strip generated tokens (they are not part of the input text).
    if generated_count and len(tokens) > generated_count:
        tokens = tokens[:-generated_count]
        token_logprobs = token_logprobs[:-generated_count]

    results: list[tuple[str, float]] = []
    for tok, lp in zip(tokens, token_logprobs, strict=True):
        if lp is None:
            # First token has no conditioning context — treat as high-info.
            results.append((tok, STATIC_OOV_SCORE))
        else:
            # Convert natural-log probability to bits of self-information.
            results.append((tok, -lp / _LN2))

    return results
