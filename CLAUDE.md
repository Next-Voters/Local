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
- **Critical**: `main.py` does NOT auto-load `.env`; it expects env vars to be present in the shell
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
  → politician_commentary → report_formatter → [email_sender (optional)]
```

Email dispatch is **decoupled from the pipeline** — it runs as a post-pipeline batch operation in the container runner after all (city, topic) pipelines complete. Reports are cached via `report_cache`, optionally translated to Spanish/French via DeepL SDK, then dispatched to subscribers in their preferred language filtered by their topic preferences.

**Key design**: Each node is a thin `RunnableSequence` that transforms pipeline state (`ChainData` TypedDict).

### Core Components

**Agents** (`agents/`):
- `base_agent_template.py`: Shared ReAct agent template with reflection context management
- `legislation_finder.py`: Discovers legislation sources via web search + reliability filtering
- `political_commentary_finder.py`: Finds elected officials and their public statements

**Pipeline Nodes** (`pipelines/node/`):
- `legislation_finder.py`: Calls the ReAct agent, returns filtered URLs
- `content_retrieval.py`: Fetches page content via markdown.new service
- `note_taker.py`: Compresses raw content into dense notes (single LLM call)
- `summary_writer.py`: Structured extraction of key legislative details (schema: `WriterOutput`)
- `politician_commentary.py`: Calls ReAct agent for political context
- `report_formatter.py`: Builds final markdown document
- `email_dispatcher.py`: Post-pipeline batch email delivery — queries subscribers' topic and language preferences, builds per-subscriber content from matching topics in their preferred language (English/Spanish/French), sends in waves of 100 with rate limiting
- `email_sender.py`: Legacy per-pipeline email node (uses shared `SMTPConnectionPool` from `utils/email.py`)

**Utilities** (`utils/`):
- `llm/`: LLM factory (`get_llm()`, `get_structured_llm()`) with default config (gpt-5, temp=0, max_tokens=16384)
- `schemas/`:
  - `state.py`: `ChainData` TypedDict (pipeline state contract)
  - `pydantic.py`: Structured output schemas (e.g., `WriterOutput`)
- `mcp/`: Per-service MCP (Model Context Protocol) client + server pairs for Tavily search/extraction, Wikidata reliability analysis, and political figure discovery. Each service lives in its own subdirectory (`tavily/`, `wikidata/`, `political_figures/`) with a `client.py` and `server.py`. Agents call `client.py` functions; `server.py` runs as a FastMCP subprocess via stdio transport. `session.py` provides `MCPSessionManager` for reusing subprocesses across tool calls within one agent invocation (avoids spawning a new process per tool call). Note: DeepL translation was moved out of MCP into a direct SDK call (`utils/report_translator.py`).
- `report_cache.py`: Module-level in-memory cache for city+topic pipeline reports and their translations. Reports are stored via `store(city, topic, report)` keyed as `{city: {topic: report}}`. Translations are stored in a parallel `_translations` dict via `store_translation(city, topic, lang, report)` or `store_all_translations(translations)`, keyed as `{city: {topic: {lang: report}}}`. Retrieve translations via `get_translation(city, topic, lang)` or `get_all_translations()`. The module itself acts as a singleton — import `from utils import report_cache` from anywhere.
- `email.py`: Consolidated email utilities — `SMTPConnectionPool` (thread-safe, context manager, NOOP health checks for stale connections), `is_email_configured()`, `load_template()`, `convert_markdown_to_html()`, `render_template()`, `create_mime_message()`, `send_single_email()`. Single source of truth for all SMTP and email rendering logic.
- `report_translator.py`: Translates all cached pipeline reports to Spanish (ES) and French (FR) synchronously via the DeepL SDK (`deepl` Python package). Uses direct `deepl.Translator` calls (no MCP layer). Exports `LANG_MAP` dict mapping language names to codes (e.g. `{"Spanish": "ES", "French": "FR"}`). Optional — gracefully skipped if `DEEPL_API_KEY` is not set.
- `context_compressor.py`: LLMLingua-2 wrapper (`compress_text()`) that semantically compresses raw page content before it enters pipeline state, preventing context overflow on large cities.
- `supabase_client.py`: Loads supported cities, topics, and languages from Supabase, manages subscriptions with topic and language preferences via the `subscription_topics` junction table and `preferred_language` FK

**Templates** (`templates/`):
- `email_report.html`: Branded HTML email template with `{{CONTENT}}` placeholder, responsive design, dark theme with red accent (#E63946), `{{UNSUBSCRIBE_URL}}` footer link

**Configuration** (`config/`):
- `system_prompts/`: Prompt templates for agents and nodes
- `search_profiles/`: Tavily search profile YAML files (`legislation.yaml`, `political.yaml`) that control domain allow-lists, date windows, and query structure (city-specific query refinement)
- `constants.py`: Pipeline-wide tuneable constants: `COMPRESSION_RATE`, `MIN_CHARS_TO_COMPRESS`, `MAX_AGENT_MESSAGES`, `MAX_REFLECTION_ENTRIES`, `AGENT_RECURSION_LIMIT`

### Data Flow Example

1. **Legislation Finder**: Agent uses Tavily search (via MCP) + Wikidata reliability check (via MCP) → outputs list of vetted URLs
2. **Content Retrieval**: Fetches each URL's text via Tavily Extract (with `markdown.new` as fallback); each block is then compressed by LLMLingua-2 before being stored → list of compressed text blocks
3. **Note Taker**: LLM summarizes all blocks into dense notes
4. **Summary Writer**: LLM extracts structured data (title, category, impact, etc.) → `WriterOutput`
5. **Politician Commentary**: Agent discovers officials via Political Figures MCP, searches statements via Tavily MCP, and searches Twitter via tweepy → politician public statements
6. **Report Formatter**: Combines all outputs into markdown for display/email
7. **Post-pipeline** (container runner only): Reports are translated to Spanish and French via the DeepL SDK, stored in the report cache translations layer, then dispatched to each subscriber in their preferred language (from `subscriptions.preferred_language`) filtered by their topic preferences

### Key Design Decisions

**Fixed pipeline over dynamic routing**
- Nodes execute in fixed order, making behavior predictable and debuggable
- Changes to pipeline structure happen at `pipelines/nv_local.py:chain`

**ReAct agents only for tool-use**
- Legislation and political commentary discovery use ReAct (multi-turn reasoning with tools)
- Note-taking and summary-writing are single-shot LLM transforms (simpler, cheaper)

**Reliability gate before content fetching**
- URLs are validated using Wikidata (via MCP) + structured LLM output (`SourceReliabilityJudgment`) before fetching
- Pydantic-enforced structured output replaced the earlier manual JSON parsing that could silently produce wrong results; now a parse failure raises rather than silently passing bad data

**Content extraction via Tavily Extract (not markdown.new)**
- `content_retrieval.py` uses the Tavily Extract SDK as its primary extraction method; `markdown.new` remains as a fallback for domains Tavily cannot reach
- This replaced a pattern where some sites returned 403s via `markdown.new`, producing empty content and empty reports

**Semantic context compression (LLMLingua-2) per source**
- Each fetched page is independently compressed by `utils/context_compressor.py` (BERT-based token classifier) before entering pipeline state
- Content retrieval caps URLs at 10 (down from 20) to prevent context overflow on content-rich cities like NYC
- At `COMPRESSION_RATE=0.4` with the 10-URL cap, even large-city payloads stay safely under the 272K-token input limit — avoiding `OpenAIContextOverflowError`
- Compression is applied per-source (not once on the concatenated batch) to keep the logic local to where data enters the pipeline
- Short content (<1000 chars) bypasses compression entirely; model is lazy-loaded on first use, no API key or GPU required

**MCP server architecture for all external tools**
- All agent tools are thin inline adapters that call FastMCP servers via stdio transport — no custom HTTP clients or manual JSON handling
- Each service (`tavily/`, `wikidata/`, `political_figures/`) has a `server.py` that owns the business logic and a `client.py` that manages the session lifecycle
- The earlier `tools/` directory (shared tool functions passed to agents) was eliminated; tool adapters now live directly in each agent file
- `MCPSessionManager` (in `utils/mcp/session.py`) pre-initializes one subprocess per agent invocation and reuses it across all tool calls, preventing the process-per-call overhead that was producing process termination warnings

**Rate limiting: bounded agent iterations**
- Pipeline nodes pass `AGENT_RECURSION_LIMIT=25` (from `config/constants.py`) at `ainvoke()` time via the `config` dict, preventing unbounded tool call loops that caused 429 Too Many Requests errors in multi-city runs
- System prompts for both agents include explicit "Exit Criteria" sections with measurable stopping conditions; `search_political_commentary` defaults to `max_results=3` (was 5)
- Together these reduce LLM request volume ~40% while maintaining research quality

**In-memory report cache (`utils/report_cache.py`)**
- Module-level nested dict cache keyed by `{city: {topic: report}}`
- Reports are cached incrementally via `report_cache.store(city, topic, report)` as each pipeline thread completes
- The email dispatcher receives reports via `report_cache.get_all()`, which returns a deep copy (`dict[str, dict[str, str]]`)
- Any component can access cached reports by importing the module: `from utils import report_cache`
- Empty/falsy reports are silently skipped by `store()`, matching the previous filtering behavior
- Cache is cleared between runs via `clear()` or `build_from_results()`

**Decoupled email dispatch with topic filtering**
- Email sending was removed from the pipeline chain; it now runs as a post-pipeline batch operation in `runners/run_container_job.py`
- After all (city, topic) pipelines complete, `report_cache.get_all()` provides all reports, which are translated via `report_translator.translate_all_reports()` then dispatched via `email_dispatcher.dispatch_emails_to_subscribers()`
- Each subscriber receives only reports matching their topic preferences (queried from `subscription_topics` junction table in Supabase)
- Emails are sent in waves of 100 with 1-second delays to avoid SMTP rate limiting

**Thread-safe SMTP connection pool (`utils/email.py`)**
- `SMTPConnectionPool` manages a `queue.Queue` of reusable SMTP connections with configurable pool size (default 10)
- `get_connection()` validates connections with SMTP NOOP before returning; stale/dead connections are discarded and replaced
- Supports context manager protocol (`with pool:`) for automatic cleanup
- `close_all()` uses a direct `get_nowait()` loop (fixed TOCTOU race from earlier `while not empty()` pattern)
- All email sending code imports from `utils/email.py` as the single source of truth

**Language-aware multilingual reports via DeepL SDK**
- Reports are optionally translated to Spanish (ES) and French (FR) via the `deepl` Python SDK (direct synchronous API calls)
- `utils/report_translator.py` translates all cached reports sequentially using a single `deepl.Translator` instance
- Translations are stored in `report_cache._translations` via `store_all_translations()` alongside the original English reports
- Subscribers receive emails in their `preferred_language` (from `subscriptions` table); English or NULL defaults to the original report
- `supported_languages` lookup table constrains valid language values; `subscriptions.preferred_language` is a nullable FK to it
- Gracefully skipped if `DEEPL_API_KEY` is not set (free tier: 500K chars/month)

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
- `TAVILY_API_KEY`: Tavily Search + Extract (web search and content retrieval via MCP)

**Optional**:
- `TWITTER_BEARER_TOKEN`: Twitter/X search via tweepy SDK in Political Figures MCP server (bearer token only; v2 API does not use `TWITTER_API_KEY`)
- `SUPABASE_URL`, `SUPABASE_KEY`: Load supported cities + email subscribers
- `SMTP_EMAIL`, `SMTP_APP_PASSWORD`: Send reports via SMTP

**External APIs** (no env needed, service-to-service):
- Wikidata REST + SPARQL (source reliability checking via Wikidata MCP server)
- OpenStreetMap Nominatim (country detection)
- OpenNorth Represent (Canada) + WeVote API (USA) for political figures (via Political Figures MCP server)

**Local models** (downloaded on first run, no API key):
- `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` (HuggingFace Hub) — used by `utils/context_compressor.py` for content compression; cached after first download, runs on CPU

## Common Patterns

**State Passing**
- Pipeline state is a `ChainData` TypedDict. Each node receives it as input, modifies relevant fields, and returns it.
- Example: `legislation_finder_node` receives `{"city": str, "topic": str}`, returns `{"city": str, "topic": str, "legislation_sources": list[str], ...}`

**LLM Calls**
- Structured output: use `get_structured_llm(OutputSchema)` → returns a Runnable that enforces schema
- Unstructured: use `get_llm()` → invoke with list of messages

**Agents**
- Inherit from `BaseReActAgent` (see `agents/base_agent_template.py`)
- Tools are defined as inline adapter functions directly inside each agent file (not in a separate `tools/` directory — that was deleted in PR #36)
- Each tool adapter calls the appropriate MCP client function and returns a LangGraph `Command` for state updates
- Agent builds a LangGraph StateGraph with `call_model` and `tool_node` nodes; `recursion_limit` is applied at invoke-time via the config dict (not at compile-time)

**Error Handling**
- Classifier output parse failures → reject all sources (safe fallback)
- Missing email env vars → skip email dispatch (silent skip, not error)
- Missing `DEEPL_API_KEY` → skip translation (returns empty dict, emails sent in English only)
- Per-city failures in multi-city runs are captured and logged; pipeline continues for other cities

## Code Conventions

- **Typed data structures**: Use `TypedDict` or Pydantic models at pipeline boundaries (between nodes, agents, external APIs)
- **No dedicated config file**: Configuration is inlined (e.g., `DEFAULT_LLM_CONFIG` in `utils/llm/config.py`)
- **Minimal dependencies**: Only essential packages in `requirements.txt`; MCP clients are lightweight wrappers
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

- Political commentary schema still evolving; if agent returns non-empty data in unexpected shape, report formatting may fail
- LLMLingua-2 downloads `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` from HuggingFace on first run (~400MB); cold starts in containerized environments will be slow until the model is cached
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
1. Define the tool adapter as an inline function directly in the agent file (e.g., `agents/legislation_finder.py`) with LangChain `@tool` decorator — the `tools/` directory no longer exists
2. If the tool needs an external service, add the logic to the appropriate MCP server (`utils/mcp/<service>/server.py`) and call it from a client function (`utils/mcp/<service>/client.py`)
3. Pass the tool adapter to the agent constructor; it is automatically included in `ToolNode`

**Changing LLM model or config**:
1. Update `utils/llm/config.py:DEFAULT_LLM_CONFIG`
2. Note: All LLM factory functions reference this dict, so one change affects all calls

**Debugging a city pipeline failure**:
1. Run single city: `python main.py <city_name>` (no -q flag to see output)
2. Check error message in stdout/stderr
3. Likely causes: missing env vars (`OPENAI_API_KEY`, `TAVILY_API_KEY`), Tavily Extract failure on a domain, MCP subprocess initialization error (check that project root is on `sys.path`), agent hitting `recursion_limit=25` before completing, LLMLingua-2 model download failing on cold start
4. Look at per-city result dict in `runners/run_container_job.py:main()` for error field