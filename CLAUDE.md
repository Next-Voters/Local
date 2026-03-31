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
- The main entrypoint is `main.py` → `runners/run_container_job.py` → `pipelines/nv_local.py`

### Common Commands

```bash
# Compile check (catches syntax errors early)
python -m compileall -q .

# Run pipeline for a single city (requires OPENAI_API_KEY + BRAVE_SEARCH_API_KEY)
python main.py <city_name>

# Run pipeline with custom output file
python main.py <city_name> -o report.md

# Suppress stdout report
python main.py <city_name> -q
```

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
- `email_dispatcher.py`: Async batch email delivery to Supabase subscribers

**Utilities** (`utils/`):
- `llm/`: LLM factory (`get_llm()`, `get_structured_llm()`) with default config (gpt-5, temp=0, max_tokens=16384)
- `schemas/`:
  - `state.py`: `ChainData` TypedDict (pipeline state contract)
  - `pydantic.py`: Structured output schemas (e.g., `WriterOutput`)
- `mcp/`: MCP (Model Context Protocol) client wrappers for Brave Search, Twitter, etc.
- `supabase_client.py`: Loads supported cities from Supabase, manages subscriptions

**Configuration** (`config/`):
- `system_prompts/`: Prompt templates for agents and nodes
- `search_profiles/`: Goggles profiles for Brave Search (city-specific query refinement)

### Data Flow Example

1. **Legislation Finder**: Agent uses web search + Wikidata reliability check → outputs list of vetted URLs
2. **Content Retrieval**: Fetches each URL's text via markdown.new → list of text blocks
3. **Note Taker**: LLM summarizes all blocks into dense notes
4. **Summary Writer**: LLM extracts structured data (title, category, impact, etc.) → `WriterOutput`
5. **Politician Commentary**: Agent searches for elected officials and their statements on the issue
6. **Report Formatter**: Combines all outputs into markdown for display/email

### Key Design Decisions

**Fixed pipeline over dynamic routing**
- Nodes execute in fixed order, making behavior predictable and debuggable
- Changes to pipeline structure happen at `pipelines/nv_local.py:chain`

**ReAct agents only for tool-use**
- Legislation and political commentary discovery use ReAct (multi-turn reasoning with tools)
- Note-taking and summary-writing are single-shot LLM transforms (simpler, cheaper)

**Reliability gate before content fetching**
- URLs are validated using Wikidata + a small-model classifier before fetching
- Unparseable classifier output safely rejects all sources (fail-safe pattern)

**HTML→Markdown via external service**
- Content retrieval delegates to `https://markdown.new/` instead of local HTML parsing
- Trade-off: simpler code but introduces external dependency that can fail on some domains

**Concurrency model**
- `runners/run_container_job.py` uses `ThreadPoolExecutor` for multi-city runs
- One city per thread; no shared state between cities (safe for concurrent execution)

## LLM Configuration

Default config in `utils/llm/config.py`:
- **Model**: `gpt-5`
- **Temperature**: 0.0 (deterministic)
- **Max tokens**: 16384
- **Timeout**: 60s

Use `get_llm()`, `get_mini_llm()` (same config), or `get_structured_llm(schema)` to instantiate. All pull from env var `OPENAI_API_KEY`.

## External Dependencies & Environment Variables

**Core** (required):
- `OPENAI_API_KEY`: OpenAI API access
- `BRAVE_SEARCH_API_KEY`: Brave Search via MCP

**Optional**:
- `TWITTER_API_KEY`, `TWITTER_BEARER_TOKEN`: Twitter/X search via MCP
- `SUPABASE_URL`, `SUPABASE_KEY`: Load supported cities + email subscribers
- `SMTP_EMAIL`, `SMTP_APP_PASSWORD`: Send reports via SMTP

**External APIs** (no env needed, service-to-service):
- Wikidata REST + SPARQL (source reliability checking)
- OpenStreetMap Nominatim (country detection)
- OpenNorth Represent (Canada) + WeVote API (USA) for political figures
- markdown.new (content extraction)

## Common Patterns

**State Passing**
- Pipeline state is a `ChainData` TypedDict. Each node receives it as input, modifies relevant fields, and returns it.
- Example: `legislation_finder_node` receives `{"city": str}`, returns `{"city": str, "legislation_sources": list[str], ...}`

**LLM Calls**
- Structured output: use `get_structured_llm(OutputSchema)` → returns a Runnable that enforces schema
- Unstructured: use `get_llm()` → invoke with list of messages

**Agents**
- Inherit from `BaseReActAgent` (see `agents/base_agent_template.py`)
- Define tools as functions, then pass to agent constructor
- Agent builds a LangGraph StateGraph with `call_model` and `tool_node` nodes

**Error Handling**
- Classifier output parse failures → reject all sources (safe fallback)
- Missing email env vars → skip email dispatch (silent skip, not error)
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
docker run -e OPENAI_API_KEY=... -e BRAVE_SEARCH_API_KEY=... nv-local
```

**Azure (CI/CD)**:
- GitHub Actions workflow: `/.github/workflows/push-container-to-azure.yml`
- Trigger: commit message is exactly "release" or manual `workflow_dispatch`
- Output: image tagged with git SHA + "latest" pushed to Azure Container Registry
- Runtime: Azure Container Apps Job with scheduler

**Logs**: Emitted to stdout/stderr; collected by Azure Monitor in production.

## Important Known Issues / WIP

- Political commentary schema still evolving; if agent returns non-empty data in unexpected shape, report formatting may fail
- Some domains fail with markdown.new extraction (rare but documented)
- No persistent report storage by default (pipeline is stateless)

## Common Development Tasks

**Adding a new pipeline node**:
1. Create file in `pipelines/node/<node_name>.py`
2. Define node as a `RunnableSequence` or callable
3. Insert into `pipelines/nv_local.py:chain` in correct position
4. Update `utils/schemas/state.py:ChainData` if new state fields are needed
5. Document in `docs/ARCHITECTURE.md`

**Adding an agent tool**:
1. Define tool function in `tools/<agent_name>.py` with LangChain `@tool` decorator
2. Pass to agent constructor
3. Agent automatically builds `ToolNode` via `ToolNode(tools=[...])` in graph

**Changing LLM model or config**:
1. Update `utils/llm/config.py:DEFAULT_LLM_CONFIG`
2. Note: All LLM factory functions reference this dict, so one change affects all calls

**Debugging a city pipeline failure**:
1. Run single city: `python main.py <city_name>` (no -q flag to see output)
2. Check error message in stdout/stderr
3. Likely causes: missing env vars, URL fetch failure (markdown.new), classifier parsing error, external API timeout
4. Look at per-city result dict in `runners/run_container_job.py:main()` for error field