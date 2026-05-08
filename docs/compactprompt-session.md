# CompactPrompt Token Pruning: Engineering Session Log

**Author**: Krishiv Thakuria
**Date**: May 2, 2026
**Project**: Next Voters Local— multi-agent AI pipeline for municipal legislation research
**PR**: Next-Voters/Local#79 (squash merged)
**Diff**: 14 files changed, 596 insertions, 59 deletions

---

## Problem

Next Voters Local discovers, researches, and summarizes municipal legislation across cities using a LangGraph-based multi-agent pipeline. Each pipeline run fetches 10 web pages of legislative content, compresses them, and feeds them to downstream LLM calls for note-taking and structured extraction.

The compression layer was using **head truncation** — `text[:target_chars]` — which discards everything after a character cutoff. This is a lossy, position-biased heuristic: important legislative details at the end of a page (vote tallies, amendment language, effective dates) are silently dropped. The system worked, but information loss was a known ceiling on report quality.

The prior approach (LLMLingua-2, a 1GB BERT-based compression model) had already been removed in [PR #75](https://github.com/Next-Voters/Local/pull/75) because it was too heavy for Docker container deployment. The codebase still contained stale references to it.

## Approach: Why CompactPrompt

I implemented the **hard prompt pruning** technique from [CompactPrompt (arXiv:2510.18043)](https://arxiv.org/abs/2510.18043) — a token-level scoring method that removes low-information tokens while preserving high-information ones regardless of their position in the document.

The core idea: every token gets a **self-information score** measuring how much information it carries. Low-scoring tokens (filler words, boilerplate) are pruned. High-scoring tokens (legislative terms, proper nouns, numbers) are kept. A phrase grouper prevents syntactic units from being broken apart.

### Why not paragraph-level pruning?

Modern chat models (GPT-4o, GPT-5) only provide logprobs on output tokens, not input tokens. This limits dynamic scoring to paragraph-level granularity — send paragraphs, score the model's summary, prune low-scoring paragraphs. I rejected this because legislative text has a pattern where critical details (vote counts, dates, amendment language) are embedded in otherwise low-information paragraphs. Paragraph-level pruning would miss these.

### Finding token-level logprobs

I needed a model that returns per-input-token log probabilities. OpenAI's current chat models don't support this. After researching providers:

| Provider | Model | Input Cost | Context | Input Logprobs |
|----------|-------|-----------|---------|----------------|
| **Together AI** | GPT-OSS-20B | $0.03/1M tokens | 131K | Yes (`echo=true`) |
| Fireworks AI | Various | ~$0.10/1M | Varies | Yes |
| vLLM (self-hosted) | Any | Infra cost | Varies | Yes |

**GPT-OSS-20B** is OpenAI's open-weight MoE model (21B total params, 3.6B active). Together AI hosts it at $0.03/1M tokens with the legacy completions API (`echo=true`, `logprobs=5`), which echoes back all input tokens with their conditional probabilities. This gives exactly the signal needed for token-level dynamic self-information: `I_dyn(t) = -log2(P(t|context))`.

Cost per full multi-city container run (15 cities x 3 topics x 10 URLs): **$0.135**.

## Architecture

Two-signal blended scoring at token level:

```
                    +-----------------+
   Raw text ------->| Together AI     |-----> I_dynamic per token
                    | GPT-OSS-20B    |       (context-aware)
                    | echo=true      |
                    +-----------------+
                            |
                            v
                    +-----------------+
                    | Blending        |-----> Blended score per token
                    | delta <= 0.1?   |       (static regularizes dynamic)
                    +-----------------+
                            ^
                            |
   Raw text ------->+-----------------+
                    | wordfreq        |-----> I_static per token
                    | (unigram freq)  |       (corpus-based)
                    +-----------------+

                    +-----------------+
   Blended scores ->| SpaCy           |-----> Phrase-aware pruning
   + BPE tokens     | en_core_web_sm  |       (keeps syntactic units)
                    +-----------------+
                            |
                            v
                       Pruned text
```

**Blending formula** (from the paper): `delta = |I_dyn - I_stat| / I_stat`. If `delta <= 0.1`, use the arithmetic mean (signals agree). Otherwise, use the dynamic score (context knows something the corpus doesn't).

**Query boost**: Tokens matching the pipeline's topic query get a 1.5x score multiplier, so topic-relevant content is preserved even if statistically common.

**Phrase grouping**: SpaCy `en_core_web_sm` extracts noun chunks, named entities, and compound chains. A token below the pruning threshold is kept if its phrase group's mean score exceeds the threshold. This prevents breaking apart "City Council", "Ordinance 2024-157", or "January 15, 2024".

**Fallback chain** (the pipeline never crashes):

| Level | Trigger | Behavior |
|-------|---------|----------|
| Full pruning | Happy path | Static + dynamic + phrase grouping |
| Static-only | Together AI down or no API key | Static scores via wordfreq only |
| Head truncation | Unexpected error in pruner | `text[:target_chars]` (original behavior) |

## What I Built

### New Modules (4 files, 536 lines)

**`utils/content/static_scorer.py`** — Static self-information via `wordfreq` library. Pre-computed unigram frequencies from Wikipedia, Reddit, Google Books (~57MB package, no custom corpus needed). Pure lookup, O(n), thread-safe.

Verified output: "the" = 4.2 bits, "Council" = 13.0 bits, "Ordinance" = 17.9 bits, "zoning" = 16.9 bits. Legislative terms score high; filler scores low. Unknown tokens (OOV) get a conservative 22.0 bits — preserved, never pruned.

**`utils/content/dynamic_scorer.py`** — Together AI client for GPT-OSS-20B logprobs. Sends full document with `echo=true`, `logprobs=5`, `max_tokens=1`. Returns `(token_string, I_dynamic)` pairs for every input token. Retry logic with exponential backoff, safe `Retry-After` header parsing.

**`utils/content/phrase_grouper.py`** — SpaCy `en_core_web_sm` dependency-based phrase grouping. Extracts noun chunks, named entities, and compound/nummod chains. Maps SpaCy character spans to BPE token indices. Merges overlapping groups via union-find. Returns empty list on failure (graceful degradation).

**`utils/content/pruner.py`** — Orchestrator. Blends scores, applies query boost, enforces phrase constraints, computes percentile threshold, reassembles kept tokens. Drop-in replacement for the former head truncation: same function signature (`prune_text(text, rate, query)`), same return type.

### Modified Modules (10 files, 60 lines changed)

- **`utils/content/compressor.py`** — Rewired to delegate to `pruner.prune_text()` with head-truncation fallback on any exception
- **`config/constants.py`** — Added 6 pruning constants (model name, timeout, retries, blend threshold, query boost factor, OOV score)
- **`requirements.txt`** — Removed `llmlingua`, added `spacy>=3.7` and `wordfreq>=3.1`
- **`docker/Dockerfile`** — Added `python -m spacy download en_core_web_sm` to build step
- **`.env.example`** — Added `TOGETHER_API_KEY`
- **`config/system_prompts/compression.py`** — Deleted (dead code, never imported)
- **`config/system_prompts/__init__.py`** — Removed dead export
- **`pipelines/node/content_retrieval.py`** — Updated stale LLMLingua comments
- **`docs/ARCHITECTURE.md`** — Updated architecture descriptions
- **`CLAUDE.md`** — Updated project documentation

## Decision Log

### "Why not use a local model?"

This pipeline runs in a Docker container on Azure Container Apps. A BERT-based compressor (LLMLingua-2) was previously removed because its 1GB model download and GPU-free inference latency were impractical. Together AI at $0.03/1M tokens is cheaper than the compute cost of hosting a local model, with no cold start.

### "Why wordfreq instead of building a frequency table?"

`wordfreq` bundles pre-computed frequencies from a massive blended corpus (Wikipedia, Reddit, Google Books, OpenSubtitles) as a pip-installable package. No corpus building, no file management, no Docker volume mounts. ~90% of BPE tokens from Together AI are whole words that `wordfreq` handles correctly. The ~10% subword fragments get the conservative OOV default (preserved, never pruned). Since dynamic scoring is the primary signal, this coverage is sufficient.

### "Why GPT-OSS-20B specifically?"

It's the cheapest model with input token logprobs on a hosted API. 3.6B active parameters (MoE architecture) means fast inference. 131K context handles even the longest legislative pages. The model doesn't need to be smart — it's used as a probability distribution, not a reasoning engine.

### "Why not implement n-gram abbreviation too?"

The CompactPrompt paper describes three techniques: hard prompt pruning, n-gram abbreviation, and uniform quantization. I implemented only pruning because it delivers the largest compression gain with the least complexity. N-gram abbreviation is planned for a future iteration.

## Bugs Found and Fixed

I ran two rounds of automated stress testing (spawning dedicated review agents) that caught 7 bugs before merge:

| Bug | Severity | Root Cause | Fix |
|-----|----------|-----------|-----|
| Generated token leaked into output | Critical | Together AI with `echo=true` and `max_tokens=1` returns N prompt tokens + 1 generated token | `_parse_response` strips last `generated_count` tokens |
| BPE/SpaCy text mismatch | High | `"".join(bpe_tokens)` may differ from original text (whitespace, unicode) | Pass reconstructed text to SpaCy instead of original |
| Whitespace fallback broke phrase grouper | High | `text.split()` loses whitespace, making character offset mapping impossible | Skip phrase grouping entirely in fallback path |
| SpaCy model missing in Docker | High | `en_core_web_sm` requires separate download step | Added to Dockerfile RUN step |
| `Retry-After` header crash | Medium | `int("Thu, 01 Jan 2026...")` raises ValueError on HTTP date format | Wrapped in try/except with fallback to 2s |
| Query boost missed multi-word BPE tokens | Low | Exact match failed on tokens like `" housing policy"` | Changed to substring matching |
| Pruner returned empty string | Low | Aggressive pruning could eliminate all tokens | Added safety floor returning original text |

## Metrics

- **Session duration**: ~3 hours (single sitting, research through merge)
- **Tool calls**: 177 (reads, edits, writes, bash, web searches, agent spawns)
- **Files touched**: 14
- **Lines added**: 596
- **Lines removed**: 59
- **Bugs caught pre-merge**: 7
- **Stress test rounds**: 2 (automated agent-based code review)
- **Cost per pipeline run**: $0.003 (single city) / $0.135 (full multi-city container)

## Thread Safety

All components safe for `ThreadPoolExecutor` (the pipeline's existing concurrency model):
- `wordfreq`: thread-safe (read-only internal data)
- SpaCy: `nlp(text)` is thread-safe (model loaded once via `lru_cache`)
- Together AI: independent `httpx` requests per thread
- No shared mutable state between pipeline instances
