"""Pipeline-wide configuration constants."""

# ---------------------------------------------------------------------------
# Content retrieval — adaptive caps
# ---------------------------------------------------------------------------

# Hard ceiling on URLs fed to the content-retrieval step. Tavily Extract
# itself can handle 20 URLs per batch; the tighter cap here bounds the
# downstream LLM context, not the API.
CONTENT_MAX_URLS: int = 10

# Total character budget for raw (pre-compression) content across all URLs
# in a single pipeline run. Per-URL allocation scales this by URL count.
# At COMPRESSION_RATE=0.4 a 150K-char raw budget compresses to ~60K chars
# (~15K tokens) for the note-taker — well inside the 272K-token input cap.
CONTENT_TOTAL_CHAR_BUDGET: int = 150_000

# Per-URL floor and ceiling to keep a small-city run from starving and a
# content-rich URL from monopolizing the budget.
CONTENT_MIN_CHARS_PER_URL: int = 5_000
CONTENT_MAX_CHARS_PER_URL: int = 40_000

# Default Tavily Search results per query.
WEB_SEARCH_MAX_RESULTS: int = 5


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

