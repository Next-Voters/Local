# Search Profiles — Tavily MCP Infrastructure

This document explains how the Tavily search profile system works, why it exists, and how it shapes the legislation-finding pipeline.

## Problem

The pipeline needs to find municipal legislation for any supported city — including cities outside the United States. An early design used domain whitelists (`include_domains`) to restrict Tavily results to a handful of known-good sites (Legistar, Municode, Govtrack, etc.). This broke for non-US cities like Toronto because their legislative content lives on entirely different platforms (e.g. `toronto.ca`).

The current design replaces domain whitelisting with a three-layer quality pipeline that works globally.

## Architecture

Search profiles are YAML configuration files that control how the Tavily MCP server builds and filters search requests. They sit between the agent (which constructs the raw query) and the Tavily API (which returns scored results).

```
Agent (ReAct loop)
  │
  │  raw query: "Toronto city council legislation March 28 2026"
  ▼
Tavily MCP Server (_search_with_profile)
  │
  │  1. Load YAML profile
  │  2. Build final query (prefix + query + city + suffix + terms)
  │  3. Apply Tavily API params (search_depth, topic, days, exclude_domains)
  │  4. Fetch 2x results (over-fetch to compensate for score filtering)
  │  5. Sort results by Tavily relevance score (descending)
  │  6. Drop results below min_score threshold
  │  7. Trim to requested count
  │  ▼
Agent receives scored, filtered results
  │
  │  passes sources to reliability_analysis tool
  ▼
Wikidata + LLM reliability judgment
  │
  │  accepted URLs proceed downstream
  ▼
Content Retrieval → Note Taker → Summary Writer → Report
```

### Three-layer quality pipeline

| Layer | Mechanism | Where it runs | What it catches |
|---|---|---|---|
| **1. Tavily score filter** | ML-based relevance ranking + `min_score` cutoff | `utils/mcp/tavily/server.py` | Low-relevance noise, off-topic results |
| **2. Domain exclusion** | Blocks known low-quality domains (social media, blogs, petitions) | YAML profile `exclude_domains` | User-generated content, opinion platforms |
| **3. Wikidata + LLM** | Organization lookup + structured reliability judgment | `utils/mcp/wikidata/server.py` | Unreliable publishers, advocacy groups, paywalled-only content |

This replaces the old single-layer approach (domain whitelist) that silently produced zero results for any city whose legislative platform was not in the list.

## Profile files

Profiles live in `config/search_profiles/` as YAML files. Each profile is referenced by name from the MCP tool functions in `utils/mcp/tavily/server.py`.

| File | Used by | Purpose |
|---|---|---|
| `legislation.yaml` | `search_legislation()` MCP tool | Legislation finder agent searches |
| `political.yaml` | `search_political_content()` MCP tool | Political commentary agent searches |

## YAML schema

Every field is optional. Unset fields use sensible defaults.

```yaml
# --- Identity ---
name: "Human-readable profile name"
description: "What this profile is for"

# --- Query construction ---
# These modify the agent's raw query before it hits Tavily.
# The agent already builds targeted queries, so keep these minimal
# to avoid redundancy.
query_prefix: ""           # Prepended to every query
query_suffix: ""           # Appended after city name
append_city: true          # Whether to quote-append the city name
required_terms: []         # Extra terms added to query (supports {city} template)
excluded_terms: []         # Terms prefixed with "-" (supports {city} template)

# --- Tavily API parameters ---
search_depth: "advanced"   # "basic" or "advanced" (advanced = deeper crawl)
topic: "news"              # "general", "news", or "finance"
days: 60                   # Restrict results to last N days
max_results_cap: 20        # Hard ceiling on results per search

# --- Score-based filtering ---
# Tavily returns a relevance score (0.0–1.0) for each result.
# Results below min_score are discarded before the agent sees them.
min_score: 0.35            # 0.0 = no filtering

# --- Domain filtering ---
# Exclusion-based: block known bad sources. Preferred over include_domains
# because it works globally across all cities and countries.
include_domains: []        # Only return results from these domains (use sparingly)
exclude_domains:           # Never return results from these domains
  - "twitter.com"
  - "reddit.com"
  # ...
```

## Query construction

The `_build_query` function in `utils/mcp/tavily/server.py` assembles the final Tavily query string from profile fields and the agent's raw query:

```
[query_prefix] [agent_query] ["city_name"] [query_suffix] [required_terms] [-excluded_terms]
```

For example, with the legislation profile and an agent query of `"Toronto city council bylaws April 2026"`:

```
Toronto city council bylaws April 2026 "Toronto"
```

The city is always quoted to force an exact match. The profile's `query_prefix` is intentionally left empty for legislation searches because the agent already constructs domain-specific queries — adding a prefix like `"city council legislation"` would create redundant terms that dilute Tavily's ranking.

## Score-based filtering

Tavily's relevance score is an ML-generated signal (0.0–1.0) that reflects how well each result matches the query in terms of content relevance, source authority, and freshness. The profile layer uses this score in two ways:

**1. Over-fetching**: When `min_score > 0`, the server requests `2x` the number of results the agent asked for. This compensates for results that will be dropped by the score filter.

**2. Sort and filter**: Results are sorted by score descending, filtered against `min_score`, then trimmed back to the originally requested count.

```python
# Simplified from _search_with_profile()
results.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
results = [r for r in results if r["score"] >= min_score]
results = results[:max_results]
```

The agent also sees each result's score in the tool output (e.g. `[0.78] Toronto City Council — https://...`), which gives the LLM a signal to prioritize higher-scored sources during reliability analysis.

### Choosing min_score thresholds

| Threshold | Effect | Use case |
|---|---|---|
| 0.0 | No filtering | When you want every result Tavily returns |
| 0.20–0.30 | Light filter | Broad searches where recall matters more than precision |
| 0.30–0.40 | Moderate filter | Default for legislation/political searches |
| 0.50+ | Aggressive filter | Risk of dropping valid results for niche cities |

The legislation profile uses `0.35` and the political profile uses `0.30` (political commentary is harder to find, so the threshold is more lenient).

## Domain exclusion strategy

Instead of whitelisting a few "known good" domains (which fails for any city not covered by those platforms), the profiles blacklist known low-quality source categories:

| Category | Domains | Why excluded |
|---|---|---|
| Social media | twitter.com, x.com, facebook.com, instagram.com, tiktok.com | User-generated, unverified, opinion-heavy |
| Forums | reddit.com, quora.com, nextdoor.com | Anecdotal, not authoritative |
| Blogs | medium.com, substack.com, blogspot.com, wordpress.com, tumblr.com | Opinion/editorial, not primary sources |
| Petitions | change.org, petition.parliament.uk | Advocacy, not legislation |
| Reference | wikipedia.org | Secondary source, not primary legislative content |
| Video | youtube.com | Not extractable as text |
| Community news | patch.com | Hyper-local aggregator, inconsistent quality |

Everything else is allowed through and evaluated by the downstream Wikidata + LLM reliability layer. This means government portals, established newspapers, wire services, and legislative databases from any country pass through automatically.

## Adding a new search profile

1. Create `config/search_profiles/<name>.yaml` with the fields above.
2. Add a new MCP tool function in `utils/mcp/tavily/server.py`:
   ```python
   @mcp.tool
   def search_<name>(query: str, city: str, max_results: int = 5) -> dict:
       """Search using the <name> profile."""
       return _search_with_profile(
           query=query, profile_name="<name>",
           max_results=max_results, city=city,
       )
   ```
3. Expose the tool via the Tavily MCP client in `utils/mcp/tavily/client.py`.
4. Wire it into the relevant agent as an inline tool adapter.

## Tuning for a specific city

If a city consistently returns poor results, adjust in this order:

1. **Check the agent's queries** — run with logging to see what queries the legislation finder agent constructs. Bad queries produce bad results regardless of profile settings.
2. **Lower `min_score`** — if valid results are being filtered out, reduce to `0.20` temporarily and inspect the scores of returned results.
3. **Adjust `days`** — some cities have less frequent council meetings. Increasing the window (e.g. `days: 90`) captures more activity.
4. **Add city-specific exclude_domains** — if a particular spam domain keeps appearing for one city, add it to the profile.
5. **Do not add `include_domains`** — this is the nuclear option that breaks the profile for other cities. If you must, create a separate profile for that city.

## File reference

| File | Role |
|---|---|
| `config/search_profiles/legislation.yaml` | Legislation search profile config |
| `config/search_profiles/political.yaml` | Political commentary search profile config |
| `utils/mcp/tavily/server.py` | MCP server: profile loading, query building, score filtering, Tavily API calls |
| `utils/mcp/tavily/client.py` | MCP client: session management, result extraction (includes score field) |
| `agents/legislation_finder.py` | Agent: `web_search` tool adapter that calls `search_legislation` and surfaces scores |
| `agents/political_commentary_finder.py` | Agent: tool adapter that calls `search_political_content` |
| `utils/mcp/wikidata/server.py` | Downstream reliability analysis (layer 3) |
| `config/system_prompts/reliability_judgment.py` | LLM prompt for source reliability tiering |
