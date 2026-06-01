# Agent Architecture

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
- Agent is compiled with `recursion_limit=25` to prevent unbounded tool-call loops (added after 429 rate-limit errors in multi-city runs)
- Output: `legislation_sources` (a list of URLs)

2) Content retrieval (inline in `tools/web_search.py`)

- The `web_search` tool fetches full page content via Tavily Extract after each search, then compresses it via dynamic self-information scoring (`utils/content/compressor.py`)
- Compressed content is returned in the tool message (so the researcher can read it) and pushed to state as `{"url", "content"}` dicts
- `run_agent_team.py` extracts `legislation_content` from the content dicts after source reliability filtering
- Output: `legislation_content` (list of compressed text blocks, populated in `run_agent_team.py`)

3) `pipelines/node/note_taker.py`

- Single LLM call to compress raw page text into dense notes
- Output: `notes` (plain text)

4) `pipelines/node/summary_writer.py`

- Single LLM call with a structured output schema (`utils/schemas/pydantic.py:WriterOutput`)
- Output: `legislation_summary` (or `None` if the LLM indicates no usable content)

5) `pipelines/node/report_formatter.py`

- Builds a markdown document from `legislation_summary`
- Output: `markdown_report`

## Runtime Model

- Concurrency: `runners/run_container_job.py` uses a `ThreadPoolExecutor` to run one city pipeline per thread (one thread per city; no shared state between cities).
- State passing: pipeline nodes pass a simple `TypedDict` (`utils/schemas/state.py:ChainData`) from node to node.
- Async: MCP server communication uses async Python (`asyncio`); pipeline nodes call `asyncio.run()` directly to bridge async agent entry points.

## Key Design Decisions

- **Fixed chain over dynamic routing**: the pipeline is a stable sequence, so each run is easy to reason about and operate.
- **ReAct agents only where tool-use is needed**: legislation discovery uses tools (web search). Note-taking and summary writing are single LLM transforms.
- **Source filtering in agent prompt**: the legislation finder agent's system prompt includes a source classification table that instructs it to accept government sites, legislative databases, and factual news reporting while rejecting opinion pieces, blogs, and unverified aggregators. This replaced the former Wikidata-based reliability gate.
- **Content extraction via Tavily Extract (not `markdown.new`)**: Tavily Extract is the primary extraction method; `markdown.new` is a fallback. The switch resolved a 403 cascade pattern where some city sites blocked `markdown.new`, producing empty content and empty reports.
- **Per-source context compression**: `utils/content/compressor.py` compresses each fetched page individually before it enters pipeline state. This prevents `OpenAIContextOverflowError` on large cities. Compression is per-source rather than post-concatenation so that each URL's content is bounded independently.
- **MCP server architecture for external tools**: all agent tools are thin inline adapters calling FastMCP servers over stdio. Business logic lives in the server; agents are decoupled from API specifics. This replaced the `tools/` directory, which contained agent-specific functions that mixed tool registration with API client logic.
- **Bounded agent iteration**: `recursion_limit=25` on all agent graphs + explicit "Exit Criteria" in system prompts prevent unbounded tool-call loops that caused 429 rate-limit errors in multi-city runs.

## External Dependencies

- OpenAI (via `langchain-openai`): LLM calls for all pipeline nodes
- Tavily Search + Extract (via MCP server `utils/mcp/tavily/`): web search and content extraction; replaces Brave Search and the `markdown.new` dependency
- OpenStreetMap Nominatim: country detection for a city name
- Optional: Supabase and SMTP for email delivery

## Known Gaps / WIP

- Tavily Extract can fail on JS-heavy SPAs or access-restricted domains; `markdown.new` fallback handles most cases but is not 100% reliable.
