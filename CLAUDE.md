# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Next Voters Local** is a multi-agent AI research pipeline that discovers, researches, and summarizes municipal legislation across cities. It makes government information accessible to communities that lack time or resources to track local officials.

The system runs as a standalone CLI tool or Docker container, orchestrated by LangGraph-based agents. Each execution produces a structured markdown report for a given city.

## Development Setup

### Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

- Copy `.env.example` to `.env` and set required keys
- All entrypoints and modules that read env vars call `load_dotenv()` from `python-dotenv`, so `.env` is loaded automatically
- **CLI entrypoint**: `main.py` → `pipelines/nv_local.py` (single-city, requires city argument validated against Supabase `supported_cities`)
- **Docker/Azure entrypoint**: `runners/run_container_job.py` (multi-city concurrent ingestion, must not be modified for CLI changes)

### Common Commands

```bash
# Compile check (catches syntax errors early)
python -m compileall -q .

# Run pipeline for a single city (requires OPENAI_API_KEY + TAVILY_API_KEY)
python main.py <city_name>

# Run pipeline for a city scoped to a specific topic
python main.py <city_name> -t <topic_name>

# Run pipeline with custom output file
python main.py <city_name> -o report.md

# Suppress stdout report
python main.py <city_name> -q
```

**Post-implementation verification**: After any code changes, always run `python -m compileall -q .` followed by `python main.py <city_name>` to confirm both compile-time and runtime correctness.

### Testing

There is no dedicated test suite. Quick validation:
- `python -m compileall -q .` to catch syntax errors
- Manual pipeline runs with test cities to verify data flow

## Architecture Overview

### Pipeline Structure

The pipeline is a **fixed, deterministic sequence** of nodes composed via LangGraph. This makes the execution path predictable and operational.

```
legislation_finder → content_retrieval → note_taker → summary_writer
  → report_formatter
```

Email dispatch is **decoupled from the pipeline** — it runs as a post-pipeline batch operation in the container runner after all (city, topic) pipelines complete. Reports are cached via `report_cache`, then dispatched to subscribers filtered by their topic preferences.

**Key design**: Each node is a thin `RunnableSequence` that transforms pipeline state (`ChainData` TypedDict).

### Core Components

**Agents** (`agents/`):
- `base_agent_template.py`: Shared ReAct agent template (imports reflection tool from `utils/tools`)
- `legislation_finder.py`: Discovers legislation sources via web search

**Pipeline Nodes** (`pipelines/node/`):
- `legislation_finder.py`: Calls the ReAct agent, returns URLs
- `content_retrieval.py`: Fetches page content via Tavily Extract (with `markdown.new` fallback)
- `note_taker.py`: Compresses raw content into dense notes (single LLM call)
- `summary_writer.py`: Structured extraction of key legislative details (schema: `WriterOutput`)
- `report_formatter.py`: Builds final markdown document
- `email_dispatcher.py`: Post-pipeline batch email delivery — queries subscribers' topic preferences, builds per-subscriber content from matching topics, sends in waves of 100 with rate limiting
- `email_sender.py`: Legacy per-pipeline email node (uses shared `SMTPConnectionPool` from `utils/email.py`)

**Utilities** (`utils/`):
- `llm/`: LLM factory (`get_llm()`, `get_structured_llm()`) with default config (gpt-5, temp=0, max_tokens=16384)
- `schemas/`:
  - `state.py`: `ChainData` TypedDict (pipeline state contract)
  - `pydantic.py`: Structured output schemas (e.g., `WriterOutput`)
- `report/`: Report lifecycle utilities
  - `cache.py`: Module-level in-memory cache for city+topic pipeline reports. Reports are stored via `store(city, topic, report)` keyed as `{city: {topic: report}}`. The module itself acts as a singleton — import `from utils.report import cache as report_cache` from anywhere.
  - `storage.py`: Uploads HTML reports to Supabase Storage with branded template rendering
- `content/`: Content processing and evaluation utilities
  - `compressor.py`: Context compression via `compress_text(text, rate, query)`. Retains the first `rate * len(text)` characters (head truncation). The `query` parameter is reserved for future query-aware pruning. Short content (<`MIN_CHARS_TO_COMPRESS` chars) bypasses compression.
  - `pdf_extractor.py`: PDF detection (HEAD request + suffix check) and PDF-to-Markdown conversion via pymupdf4llm.
  - `source_reliability.py`: Domain-level source reliability scoring and filtering — classifies URLs into government, legislative, news, other, or blocked tiers.
- `email.py`: Consolidated email utilities — `SMTPConnectionPool` (thread-safe, context manager, NOOP health checks for stale connections), `is_email_configured()`, `load_template()`, `convert_markdown_to_html()`, `render_template()`, `create_mime_message()`, `send_single_email()`. Single source of truth for all SMTP and email rendering logic.
- `tools/`: Agent tool adapters with LangChain `@tool` decorators, re-exported via `__init__.py` (e.g., `reflection.py`, `web_search.py`). Also contains service module `tavily.py` and a `utils/` subdirectory for helpers (`extract.py`). Google Calendar integration uses a remote MCP server (`https://gcal.mintmcp.com/mcp`) loaded via `langchain-mcp-adapters` in `agents/legislation_finder.py`.
- `supabase_client.py`: Loads supported cities and topics from Supabase, manages subscriptions with topic preferences via the `subscription_topics` junction table

**Templates** (`templates/`):
- `email_report.html`: Branded HTML email template with `{{CONTENT}}` placeholder, responsive design, dark theme with red accent (#E63946), `{{UNSUBSCRIBE_URL}}` footer link

**Configuration** (`config/`):
- `system_prompts/`: Prompt templates for agents and nodes
- `constants.py`: Pipeline-wide tuneable constants: `COMPRESSION_RATE`, `MIN_CHARS_TO_COMPRESS`, `MAX_AGENT_MESSAGES`, `MAX_REFLECTION_ENTRIES`, `AGENT_RECURSION_LIMIT`

### Data Flow Example

1. **Legislation Finder**: Agent uses Tavily search with prompt-based source filtering → outputs list of URLs
2. **Content Retrieval**: Fetches each URL's text via Tavily Extract (with `markdown.new` as fallback); each block is then compressed via `utils/content/compressor.py` → list of compressed text blocks
3. **Note Taker**: LLM summarizes all blocks into dense notes
4. **Summary Writer**: LLM extracts structured data (title, category, impact, etc.) → `WriterOutput`
5. **Report Formatter**: Combines all outputs into markdown for display/email
6. **Post-pipeline** (container runner only): Reports are uploaded to Supabase Storage, then dispatched to each subscriber filtered by their topic preferences

### Key Design Decisions

**Fixed pipeline over dynamic routing**
- Nodes execute in fixed order, making behavior predictable and debuggable
- Changes to pipeline structure happen at `pipelines/nv_local.py:chain`

**ReAct agents only for tool-use**
- Legislation discovery uses ReAct (multi-turn reasoning with tools)
- Note-taking and summary-writing are single-shot LLM transforms (simpler, cheaper)

**Source filtering in agent prompt**
- Source filtering is handled by the legislation finder agent's system prompt, which includes a classification table for accepting/rejecting sources based on type (government sites, legislative databases, factual news vs. opinion, blogs, aggregators)

**Content extraction via Tavily Extract (not markdown.new)**
- `content_retrieval.py` uses the Tavily Extract SDK as its primary extraction method; `markdown.new` remains as a fallback for domains Tavily cannot reach
- This replaced a pattern where some sites returned 403s via `markdown.new`, producing empty content and empty reports

**Per-source context compression (head truncation)**
- Each fetched page is independently compressed by `utils/content/compressor.py` before entering pipeline state. Currently uses head truncation (retains first `COMPRESSION_RATE` fraction of characters)
- Content retrieval caps URLs at 10 (down from 20) to prevent context overflow on content-rich cities like NYC
- At `COMPRESSION_RATE=0.4` with the 10-URL cap, even large-city payloads stay safely under the 272K-token input limit — avoiding `OpenAIContextOverflowError`
- Compression is applied per-source (not once on the concatenated batch) to keep the logic local to where data enters the pipeline
- Short content (<`MIN_CHARS_TO_COMPRESS=1_000` chars) bypasses compression entirely

**Direct SDK calls for external services**
- Tavily search functions live in `utils/tools/tavily.py` as direct SDK calls; tool adapters in `utils/tools/` wrap them for LangGraph
- Google Calendar uses a remote MCP server (`https://gcal.mintmcp.com/mcp`); `create_event` tool is loaded via `langchain-mcp-adapters` at agent build time in `agents/legislation_finder.py`
- Tool adapters live in `utils/tools/` with re-exports via `__init__.py`; agents import them rather than defining tools inline

**Rate limiting: bounded agent iterations**
- Pipeline nodes pass `AGENT_RECURSION_LIMIT=25` (from `config/constants.py`) at `ainvoke()` time via the `config` dict, preventing unbounded tool call loops that caused 429 Too Many Requests errors in multi-city runs
- System prompts include explicit "Exit Criteria" sections with measurable stopping conditions
- Together these reduce LLM request volume ~40% while maintaining research quality

**In-memory report cache (`utils/report/cache.py`)**
- Module-level nested dict cache keyed by `{city: {topic: report}}`
- Reports are cached incrementally via `report_cache.store(city, topic, report)` as each pipeline thread completes
- The email dispatcher receives reports via `report_cache.get_all()`, which returns a deep copy (`dict[str, dict[str, str]]`)
- Any component can access cached reports by importing the module: `from utils import report_cache`
- Empty/falsy reports are silently skipped by `store()`, matching the previous filtering behavior
- Cache is cleared between runs via `clear()` or `build_from_results()`

**Decoupled email dispatch with topic filtering**
- Email sending was removed from the pipeline chain; it now runs as a post-pipeline batch operation in `runners/run_container_job.py`
- After all (city, topic) pipelines complete, `report_cache.get_all()` provides all reports, which are dispatched via `email_dispatcher.dispatch_emails_to_subscribers()`
- Each subscriber receives only reports matching their topic preferences (queried from `subscription_topics` junction table in Supabase)
- Emails are sent in waves of 100 with 1-second delays to avoid SMTP rate limiting

**Thread-safe SMTP connection pool (`utils/email.py`)**
- `SMTPConnectionPool` manages a `queue.Queue` of reusable SMTP connections with configurable pool size (default 10)
- `get_connection()` validates connections with SMTP NOOP before returning; stale/dead connections are discarded and replaced
- Supports context manager protocol (`with pool:`) for automatic cleanup
- `close_all()` uses a direct `get_nowait()` loop (fixed TOCTOU race from earlier `while not empty()` pattern)
- All email sending code imports from `utils/email.py` as the single source of truth

**Concurrency model**
- `runners/run_container_job.py` uses `ThreadPoolExecutor` for multi-city, multi-topic runs
- One (city, topic) pair per thread; no shared state between pipeline instances (safe for concurrent execution)

## LLM Configuration

Default config in `utils/llm/config.py`:
- **Model**: `gpt-5`
- **Temperature**: 0.0 (deterministic)
- **Max tokens**: 16384
- **Timeout**: 60s

Use `get_llm()`, `get_mini_llm()` (same config as default), `get_structured_llm(schema)`, or `get_structured_mini_llm(schema)` to instantiate. All pull from env var `OPENAI_API_KEY`.

## External Dependencies & Environment Variables

**Core** (required):
- `OPENAI_API_KEY`: OpenAI API access
- `TAVILY_API_KEY`: Tavily Search + Extract (web search and content retrieval)

**Optional**:
- `SUPABASE_URL`, `SUPABASE_KEY`: Load supported cities + email subscribers
- `SMTP_EMAIL`, `SMTP_APP_PASSWORD`: Send reports via SMTP (defaults: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`)

**External APIs** (no env needed, service-to-service):
- OpenStreetMap Nominatim (country detection)

## Common Patterns

**State Passing**
- Pipeline state is a `ChainData` TypedDict. Each node receives it as input, modifies relevant fields, and returns it.
- Example: `legislation_finder_node` receives `{"city": str, "topic": str}`, returns `{"city": str, "topic": str, "legislation_sources": list[str], ...}`

**LLM Calls**
- Structured output: use `get_structured_llm(OutputSchema)` → returns a Runnable that enforces schema
- Unstructured: use `get_llm()` → invoke with list of messages

**Agents**
- Inherit from `BaseReActAgent` (see `agents/base_agent_template.py`)
- Tools are defined in `utils/tools/` and re-exported via `utils/tools/__init__.py`; agents import them (e.g., `from utils.tools import web_search`)
- Each tool adapter calls service functions from `utils/tools/tavily.py` and returns a LangGraph `Command` for state updates
- Agent builds a LangGraph StateGraph with `call_model` and `tool_node` nodes; `recursion_limit` is applied at invoke-time via the config dict (not at compile-time)

**Error Handling**
- Classifier output parse failures → reject all sources (safe fallback)
- Missing email env vars → skip email dispatch (silent skip, not error)
- Per-city failures in multi-city runs are captured and logged; pipeline continues for other cities
- SMTP connection failures are handled by the pool — stale connections replaced, delivery failures tracked in `utils/email_failures.json`

## Code Conventions

- **Typed data structures**: Use `TypedDict` or Pydantic models at pipeline boundaries (between nodes, agents, external APIs)
- **No dedicated config file**: Configuration is inlined (e.g., `DEFAULT_LLM_CONFIG` in `utils/llm/config.py`)
- **Minimal dependencies**: Only essential packages in `requirements.txt`
- **Docstrings**: Required for all functions, classes, and methods

## Deployment

**Local**: `python main.py <city>`

**Docker**:
```bash
docker build -f docker/Dockerfile -t nv-local .
docker run -e OPENAI_API_KEY=... -e TAVILY_API_KEY=... nv-local
```

**Azure (CI/CD)**:
- GitHub Actions workflow: `/.github/workflows/push-container-to-azure.yml`
- Trigger: commit message is exactly "release" or manual `workflow_dispatch`
- Output: image tagged with git SHA + "latest" pushed to Azure Container Registry
- Runtime: Azure Container Apps Job with scheduler

**Logs**: Emitted to stdout/stderr; collected by Azure Monitor in production.

## Important Known Issues / WIP

- Tavily Extract can fail on some domains (access restrictions, JS-heavy SPAs); `markdown.new` fallback handles most of these but is not 100% reliable
- No persistent report storage by default (pipeline is stateless)

## Common Development Tasks

**Adding a new pipeline node**:
1. Create file in `pipelines/node/<node_name>.py`
2. Define node as a `RunnableSequence` or callable
3. Insert into `pipelines/nv_local.py:chain` in correct position
4. Update `utils/schemas/state.py:ChainData` if new state fields are needed
5. Document in `docs/ARCHITECTURE.md`

**Adding an agent tool**:
1. Create the tool adapter function in `utils/tools/` with the LangChain `@tool` decorator, then re-export it from `utils/tools/__init__.py`
2. If the tool needs an external service, add the business logic as a plain function in the appropriate service module (e.g., `utils/tools/tavily.py`) or create a new one; shared helpers go in `utils/tools/utils/`
3. Import the tool in the agent file (e.g., `from utils.tools import web_search`) and pass it to the agent constructor; it is automatically included in `ToolNode`

**Changing LLM model or config**:
1. Update `utils/llm/config.py:DEFAULT_LLM_CONFIG`
2. Note: All LLM factory functions reference this dict, so one change affects all calls

**Debugging a city pipeline failure**:
1. Run single city: `python main.py <city_name>` (no -q flag to see output)
2. Check error message in stdout/stderr
3. Likely causes: missing env vars (`OPENAI_API_KEY`, `TAVILY_API_KEY`), Tavily Extract failure on a domain, agent hitting `recursion_limit=25` before completing, SMTP pool exhaustion (check `utils/email_failures.json`)
4. Look at per-city result dict in `runners/run_container_job.py:main()` for error field