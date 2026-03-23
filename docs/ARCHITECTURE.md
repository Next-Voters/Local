# Architecture

This repository implements a fixed, multi-step research pipeline that runs per city and produces a markdown report.

## Components

Code layout (high level):

- `main.py`: entrypoint shim that calls `pipelines/nv_local.py:main`
- `run_cli_main.py`: Rich console wrapper that loads `.env` and renders the report
- `pipelines/nv_local.py`: composes the end-to-end chain and runs it for multiple cities concurrently
- `pipelines/node/*`: individual pipeline nodes (small, single-purpose transforms)
- `agents/*`: LangGraph ReAct agents built from `agents/base_agent_template.py`
- `tools/*`: tool functions used by agents (web search, reliability checks, political figure discovery)
- `utils/*`: shared helpers (LLM factory, MCP clients, schemas, Wikidata client)

## Data Flow

`pipelines/nv_local.py` composes these nodes into a single chain:

1) `pipelines/node/legislation_finder.py`

- Calls the ReAct agent in `agents/legislation_finder.py`
- Agent tools:
  - `tools/legislation_finder.py:web_search` (Brave Search via MCP + Goggles)
  - `tools/legislation_finder.py:reliability_analysis` (Wikidata lookup + LLM classifier)
- Output: `legislation_sources` (a list of URLs that passed reliability filtering)

2) `pipelines/node/content_retrieval.py`

- Fetches each URL via `https://markdown.new/<url>` and stores the returned text
- Output: `legislation_content` (list of extracted page text blocks)

3) `pipelines/node/note_taker.py`

- Single LLM call to compress raw page text into dense notes
- Output: `notes` (plain text)

4) `pipelines/node/summary_writer.py`

- Single LLM call with a structured output schema (`utils/schemas/pydantic.py:WriterOutput`)
- Output: `legislation_summary` (or `None` if the LLM indicates no usable content)

5) `pipelines/node/politician_commentary.py`

- Calls the ReAct agent in `agents/political_commentry_finder.py`
- Agent tools:
  - `tools/political_commentry_finder.py:political_figure_finder` (OpenStreetMap Nominatim + OpenNorth Represent API for CA, WeVote API for US)
  - `tools/political_commentry_finder.py:search_political_commentary` (Brave Search + per-page LLM extraction)
  - `tools/political_commentry_finder.py:search_political_social_media` (Twitter MCP)
- Output: `politician_public_statements`

6) `pipelines/node/report_formatter.py`

- Builds a markdown document from `legislation_summary` and politician statement data
- Output: `markdown_report`

7) `pipelines/node/email_sender.py` (optional)

- If all required email env vars are present, loads subscribers from Supabase and sends the report via SMTP
- Output: no change to the report; side-effect only

## Runtime Model

- Concurrency: `pipelines/nv_local.py:run_pipelines_for_cities` uses a `ThreadPoolExecutor` to run one city pipeline per thread.
- State passing: pipeline nodes pass a simple `TypedDict` (`utils/schemas/state.py:ChainData`) from node to node.

## Key Design Decisions

- Fixed chain over dynamic routing: the pipeline is a stable sequence, so each run is easy to reason about and operate.
- ReAct agents only where tool-use is needed: legislation discovery and political commentary use tools (web search, external APIs). Note-taking and summary writing are single LLM transforms.
- Reliability gate before fetching: legislation URLs are filtered using Wikidata context and a small-model classifier; if the classifier output cannot be parsed, the safe fallback is to reject all sources.
- HTML extraction via `markdown.new`: content retrieval delegates page-to-text conversion to an external service, keeping the local code simple but introducing a dependency that can fail on some domains.

## External Dependencies

- OpenAI (via `langchain-openai`): LLM calls
- Brave Search (via Smithery-hosted MCP): web search
- Wikidata REST + SPARQL: organization metadata used for source classification
- OpenStreetMap Nominatim: country detection for a city name
- OpenNorth Represent API (Canada) and WeVote API (USA): political figure discovery
- Optional: Supabase and SMTP for email delivery

## Known Gaps / WIP

- The political commentary portion is still evolving; the report formatter expects a particular schema for public statements. If the political commentary agent returns non-empty data in a different shape, formatting may fail.
