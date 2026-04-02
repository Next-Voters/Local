# Architecture

This repository implements a fixed, multi-step research pipeline that runs per city and produces a markdown report.

## Components

Code layout (high level):

- `main.py`: entrypoint shim that calls `pipelines/nv_local.py:main`
- `run_cli_main.py`: Rich console wrapper that loads `.env` and renders the report
- `pipelines/nv_local.py`: composes the end-to-end chain and runs it for multiple cities concurrently
- `pipelines/node/*`: individual pipeline nodes (small, single-purpose transforms)
- `agents/*`: LangGraph ReAct agents built from `agents/base_agent_template.py`
- `utils/*`: shared helpers (LLM factory, MCP clients/servers, context compressor, schemas)

## Data Flow

`pipelines/nv_local.py` composes these nodes into a single chain:

1) `pipelines/node/legislation_finder.py`

- Calls the ReAct agent in `agents/legislation_finder.py`
- Agent tool adapters (defined inline in the agent file — the `tools/` directory was deleted in favour of inline adapters that call MCP servers):
  - `web_search`: calls `utils/mcp/tavily/client.py:search_legislation` (Tavily MCP server + `config/search_profiles/legislation.yaml`)
  - `reliability_analysis`: calls `utils/mcp/wikidata/client.py:analyze_reliability` (Wikidata MCP server + structured LLM output via `SourceReliabilityJudgment` Pydantic model)
- Agent is compiled with `recursion_limit=25` to prevent unbounded tool-call loops (added after 429 rate-limit errors in multi-city runs)
- Output: `legislation_sources` (a list of URLs that passed reliability filtering)

2) `pipelines/node/content_retrieval.py`

- Fetches each URL via Tavily Extract SDK (primary); falls back to `https://markdown.new/<url>` for domains Tavily cannot reach
- Each page's text is immediately compressed by `utils/context_compressor.py` (LLMLingua-2, `COMPRESSION_RATE=0.5`) before being appended to the list — this prevents `OpenAIContextOverflowError` on large cities (observed: 534K tokens for NYC > 272K limit)
- Tavily Extract is capped at 20 URLs per request (API hard limit); the pipeline respects this at both the client and node layers
- Output: `legislation_content` (list of compressed text blocks)

3) `pipelines/node/note_taker.py`

- Single LLM call to compress raw page text into dense notes
- Output: `notes` (plain text)

4) `pipelines/node/summary_writer.py`

- Single LLM call with a structured output schema (`utils/schemas/pydantic.py:WriterOutput`)
- Output: `legislation_summary` (or `None` if the LLM indicates no usable content)

5) `pipelines/node/politician_commentary.py`

- Calls the ReAct agent in `agents/political_commentary_finder.py`
- Agent tool adapters (inline in the agent file):
  - `political_figure_finder`: calls `utils/mcp/political_figures/client.py:find_political_figures` (OpenStreetMap Nominatim + OpenNorth Represent API for CA, WeVote API for US)
  - `search_political_commentary`: calls Tavily MCP for search + Political Figures MCP for per-page LLM extraction; defaults to `max_results=3` (reduced from 5 to limit API volume)
  - `search_political_social_media`: calls Political Figures MCP server, which uses tweepy SDK with `TWITTER_BEARER_TOKEN` (v2 API; no `TWITTER_API_KEY` needed)
- Agent also compiled with `recursion_limit=25`
- `MCPSessionManager` (`utils/mcp/session.py`) pre-initializes one Tavily MCP subprocess per agent invocation and reuses it across all tool calls within that invocation (eliminates process-per-call overhead)
- Output: `politician_public_statements`

6) `pipelines/node/report_formatter.py`

- Builds a markdown document from `legislation_summary` and politician statement data
- Output: `markdown_report`

7) `pipelines/node/email_sender.py` (optional)

- If all required email env vars are present, loads subscribers from Supabase and sends the report via SMTP
- Output: no change to the report; side-effect only

## Runtime Model

- Concurrency: `runners/run_container_job.py` uses a `ThreadPoolExecutor` to run one city pipeline per thread (one thread per city; no shared state between cities).
- State passing: pipeline nodes pass a simple `TypedDict` (`utils/schemas/state.py:ChainData`) from node to node.
- Async: MCP server communication uses async Python (`asyncio`); `utils/async_runner.py` provides a helper to call async functions from synchronous pipeline nodes.

## Key Design Decisions

- **Fixed chain over dynamic routing**: the pipeline is a stable sequence, so each run is easy to reason about and operate.
- **ReAct agents only where tool-use is needed**: legislation discovery and political commentary use tools (web search, external APIs). Note-taking and summary writing are single LLM transforms.
- **Reliability gate before fetching**: legislation URLs are filtered via Wikidata MCP + structured LLM output (`SourceReliabilityJudgment` Pydantic model). Structured output replaced manual JSON parsing to eliminate silent parse failures; unknown sources on recognized domains default to `conditionally_reliable` rather than being rejected outright (loosened in PR #36 to improve recall on news orgs covering city legislation).
- **Content extraction via Tavily Extract (not `markdown.new`)**: Tavily Extract is the primary extraction method; `markdown.new` is a fallback. The switch resolved a 403 cascade pattern where some city sites blocked `markdown.new`, producing empty content and empty reports.
- **Semantic context compression per source**: `utils/context_compressor.py` wraps LLMLingua-2 and compresses each fetched page individually before it enters pipeline state. This prevents `OpenAIContextOverflowError` on large cities (NYC reached 534K tokens, above the 272K model limit). Compression is per-source rather than post-concatenation so that each URL's content is bounded independently.
- **MCP server architecture for external tools**: all agent tools are thin inline adapters calling FastMCP servers over stdio. Business logic lives in the server; agents are decoupled from API specifics. This replaced the `tools/` directory, which contained agent-specific functions that mixed tool registration with API client logic.
- **Bounded agent iteration**: `recursion_limit=25` on all agent graphs + explicit "Exit Criteria" in system prompts prevent unbounded tool-call loops that caused 429 rate-limit errors in multi-city runs.

## External Dependencies

- OpenAI (via `langchain-openai`): LLM calls for all pipeline nodes
- Tavily Search + Extract (via MCP server `utils/mcp/tavily/`): web search and content extraction; replaces Brave Search and the `markdown.new` dependency
- Wikidata REST + SPARQL (via MCP server `utils/mcp/wikidata/`): organization metadata for source reliability classification
- OpenStreetMap Nominatim: country detection for a city name
- OpenNorth Represent API (Canada) and WeVote API (USA): political figure discovery (via `utils/mcp/political_figures/`)
- Twitter/X via tweepy SDK (`TWITTER_BEARER_TOKEN`): politician tweet search inside Political Figures MCP server
- LLMLingua-2 (`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`): local BERT-based token classifier for content compression; downloaded from HuggingFace Hub on first run
- Optional: Supabase and SMTP for email delivery

## Known Gaps / WIP

- The political commentary portion is still evolving; the report formatter expects a particular schema for public statements. If the political commentary agent returns non-empty data in a different shape, formatting may fail.
- LLMLingua-2 downloads ~400MB on first run; cold starts in containerized environments are slow until the model is cached in the image or a volume.
- Tavily Extract can fail on JS-heavy SPAs or access-restricted domains; `markdown.new` fallback handles most cases but is not 100% reliable.
