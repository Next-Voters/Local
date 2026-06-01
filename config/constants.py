"""Pipeline-wide configuration constants."""

# ---------------------------------------------------------------------------
# Web search — inline content extraction
# ---------------------------------------------------------------------------

# Raw content cap per URL before compression inside web_search.
# At COMPRESSION_RATE=0.4, yields ~12K chars of compressed content per URL.
WEB_SEARCH_PER_URL_CHAR_CAP: int = 30_000

# Default Tavily Search results per query.  Kept low because each search
# now triggers a Tavily Extract call (content fetched inline).
WEB_SEARCH_MAX_RESULTS: int = 3

# Raw character cap applied to each URL's content *before* compression
# inside ``web_search``.  Prevents a single large page from dominating the
# researcher agent's context window.  At COMPRESSION_RATE=0.4 this yields
# ~12 K chars of compressed content per URL.
WEB_SEARCH_PER_URL_CHAR_CAP: int = 30_000


# ---------------------------------------------------------------------------
# Context compression
# ---------------------------------------------------------------------------

# Fraction of tokens to retain after compression (0.0 = nothing, 1.0 = keep all).
# At 0.4 with a 10-URL cap, even large-city payloads stay safely under the 272 K limit.
COMPRESSION_RATE: float = 0.4

# Skip compression for content shorter than this — overhead not worth it.
MIN_CHARS_TO_COMPRESS: int = 1_000

# ---------------------------------------------------------------------------
# Token pruning (CompactPrompt blended self-information)
# ---------------------------------------------------------------------------

# Together AI model for dynamic self-information scoring.
TOGETHER_MODEL: str = "openai/gpt-oss-20b"

# Timeout for the Together AI logprobs API call (seconds).
TOGETHER_TIMEOUT: int = 60

# Maximum retries for Together AI API failures.
TOGETHER_MAX_RETRIES: int = 2

# Relative difference threshold for blending static and dynamic scores.
# When |I_dyn - I_stat| / I_stat <= this value, use arithmetic mean.
# When > this value, use dynamic score exclusively.
BLEND_DELTA_THRESHOLD: float = 0.1

# Score multiplier for tokens appearing in the pipeline topic query.
QUERY_BOOST_FACTOR: float = 1.5

# Default I_static for tokens not found in the wordfreq corpus (bits).
# Set high so unknown tokens are conservatively preserved.
STATIC_OOV_SCORE: float = 22.0

# ---------------------------------------------------------------------------
# Agent context limits
# ---------------------------------------------------------------------------

# Reflection entries kept in the agent system prompt.
MAX_REFLECTION_ENTRIES: int = 5

# ---------------------------------------------------------------------------
# Agent recursion limit
# ---------------------------------------------------------------------------

# Maximum graph steps before LangGraph raises a recursion error.
# Prevents unbounded tool-call loops in multi-city runs.
AGENT_RECURSION_LIMIT: int = 40

# Maximum researcher subagent invocations per lead-researcher execution.
# Aligns with the "2-4 specific issues" guidance in the lead researcher prompt.
MAX_RESEARCHER_INVOCATIONS: int = 4
