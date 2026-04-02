"""Pipeline-wide configuration constants."""

# ---------------------------------------------------------------------------
# Context compression (LLMLingua-2)
# ---------------------------------------------------------------------------

# Fraction of tokens to retain after compression (0.0 = nothing, 1.0 = keep all).
# At 0.5 a 534 K-token NYC payload becomes ~267 K, safely under the 272 K limit.
COMPRESSION_RATE: float = 0.5

# Skip compression for content shorter than this — overhead not worth it.
MIN_CHARS_TO_COMPRESS: int = 1_000

# ---------------------------------------------------------------------------
# Agent context limits
# ---------------------------------------------------------------------------

# Messages kept per agent _call_model invocation.
# The reflection tool maintains a rolling summary so older messages are safe to drop.
MAX_AGENT_MESSAGES: int = 30

# Reflection entries kept in the agent system prompt.
MAX_REFLECTION_ENTRIES: int = 5