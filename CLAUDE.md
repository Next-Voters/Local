# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Next Voters Local** is a multi-agent AI research pipeline that discovers, researches, and summarizes municipal legislation across cities. It makes government information accessible to communities that lack time or resources to track local officials.

The system runs as a standalone CLI tool or Docker container, orchestrated by LangGraph-based agents. Each execution researches legislation for a given city and stores structured results (headers + bullets) in Supabase.

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
- **Container entrypoint**: `main.py` with `NV_CITY` env var set (single-city, runs all topics, saves to Supabase `reports` table)

### Common Commands

```bash
# Compile check (catches syntax errors early)
python -m compileall -q .

# Run pipeline for a single city (requires OPENAI_API_KEY + TAVILY_API_KEY)
python main.py <city_name>

# Run pipeline for a city scoped to a specific topic
python main.py <city_name> -t <topic_name>

# Container mode (runs all topics for a city, saves to DB)
NV_CITY=<city_name> python main.py
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
```

**Key design**: Each node is a thin `RunnableSequence` that transforms pipeline state (`ChainData` TypedDict).

### Deployment Model (AWS)

Each city runs as an independent **ECS Fargate task**:
- **EventBridge Scheduler** triggers weekly
- **Dispatcher Lambda** fans out — one ECS task per city
- Each Fargate task runs `main.py` with `NV_CITY` env var, executing all topics sequentially
- Reports written to **Supabase Postgres** `reports` table
- After all topics complete, a `{city, report_id}` message is enqueued to **SQS**, triggering the **Email Lambda**
- If any topic or the SQS enqueue fails, failure metadata is sent to the **Pipeline DLQ** before exit 1
- **Email Lambda** (separate) reads reports and dispatches via **Amazon SES**

### Core Components

**Agents** (`agents/`):
- `base_agent_template.py`: Shared ReAct agent template (imports reflection tool from `utils/tools`)
- `legislation_finder.py`: Discovers legislation sources via web search

**Pipeline Nodes** (`pipelines/node/`):
- `legislation_finder.py`: Calls the ReAct agent, returns URLs
- `content_retrieval.py`: Fetches page content via Tavily Extract (with `markdown.new` fallback)
- `note_taker.py`: Compresses raw content into dense notes (single LLM call)
- `summary_writer.py`: Structured extraction of key legislative details (schema: `WriterOutput`)

**Utilities** (`utils/`):
- `llm/`: LLM factory (`get_llm()`, `get_structured_llm()`) with default config (gpt-5, temp=0, max_tokens=16384)
- `schemas/`:
  - `state.py`: `ChainData` TypedDict (pipeline state contract)
  - `pydantic.py`: Structured output schemas (e.g., `WriterOutput`)
- `report/`:
  - `storage.py`: Saves pipeline output to Supabase via a two-table upsert: parent `reports` row (per city+date) and child `report_headers` rows (per legislation item with topic, header, and bullets). Returns the `report_id` on success. Single function: `save_report(city, topic_name, result) → int | None`
- `content/`: Content processing and evaluation utilities
  - `compressor.py`: Context compression via `compress_text(text, rate, query)`. Retains the first `rate * len(text)` characters (head truncation). The `query` parameter is reserved for future query-aware pruning. Short content (<`MIN_CHARS_TO_COMPRESS` chars) bypasses compression.
  - `source_reliability.py`: Domain-level source reliability scoring and filtering — classifies URLs into government, legislative, news, other, or blocked tiers.
- `tools/`: Agent tool adapters with LangChain `@tool` decorators, re-exported via `__init__.py` (e.g., `reflection.py`, `web_search.py`). Contains a `utils/` subdirectory for service modules (`tavily.py`, `extract.py`). Google Calendar integration uses a remote MCP server (`https://gcal.mintmcp.com/mcp`) loaded via `langchain-mcp-adapters` in `agents/legislation_finder.py`.
- `supabase_client.py`: Loads supported cities and topics from Supabase
- `sqs_client.py`: SQS factory (`get_sqs_client()`) and message helpers (`enqueue_report()`, `enqueue_pipeline_failure()`)

**Configuration** (`config/`):
- `system_prompts/`: Prompt templates for agents and nodes
- `constants.py`: Pipeline-wide tuneable constants: `COMPRESSION_RATE`, `MIN_CHARS_TO_COMPRESS`, `MAX_REFLECTION_ENTRIES`, `AGENT_RECURSION_LIMIT`

### Data Flow Example

1. **Legislation Finder**: Agent uses Tavily search with prompt-based source filtering → outputs list of URLs
2. **Content Retrieval**: Fetches each URL's text via Tavily Extract (with `markdown.new` as fallback); each block is then compressed via `utils/content/compressor.py` → list of compressed text blocks
3. **Note Taker**: LLM summarizes all blocks into dense notes
4. **Summary Writer**: LLM extracts structured data (header + bullets per item) → `WriterOutput`
5. **Report Storage** (container mode): Upserts parent `reports` row (city+date), then `report_headers` rows (one per legislation item with topic, header, bullets). Returns `report_id`.
6. **SQS Notification** (container mode): Enqueues `{city, report_id}` to SQS so the Email Lambda can send the report. If any step failed, sends failure metadata to the Pipeline DLQ.

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
- Tavily search functions live in `utils/tools/utils/tavily.py` as direct SDK calls; tool adapters in `utils/tools/` wrap them for LangGraph
- Google Calendar uses a remote MCP server (`https://gcal.mintmcp.com/mcp`); `create_event` tool is loaded via `langchain-mcp-adapters` at agent build time in `agents/legislation_finder.py`
- Tool adapters live in `utils/tools/` with re-exports via `__init__.py`; agents import them rather than defining tools inline

**Rate limiting: bounded agent iterations**
- Pipeline nodes pass `AGENT_RECURSION_LIMIT=40` (from `config/constants.py`) at `ainvoke()` time via the `config` dict, preventing unbounded tool call loops that caused 429 Too Many Requests errors
- System prompts include explicit "Exit Criteria" sections with measurable stopping conditions
- Together these reduce LLM request volume ~40% while maintaining research quality

**Single-city Fargate tasks**
- Each ECS Fargate task runs ONE city (all topics sequentially)
- `NV_CITY` env var is validated against `supported_cities` before any API calls
- Each topic result is saved to DB immediately after pipeline completion
- After all topics, enqueues `{city, report_id}` to SQS for the Email Lambda
- If any topic fails (pipeline error, DB save failure, or SQS enqueue failure), failure metadata is sent to the Pipeline DLQ and the task exits 1

## LLM Configuration

Default config in `utils/llm/config.py`:
- **Model**: `gpt-5`
- **Temperature**: 0.0 (deterministic)
- **Max tokens**: 16384
- **Timeout**: 120s

Use `get_llm()`, `get_mini_llm()` (same config as default), `get_structured_llm(schema)`, or `get_structured_mini_llm(schema)` to instantiate. All pull from env var `OPENAI_API_KEY`.

## External Dependencies & Environment Variables

**Core** (required):
- `OPENAI_API_KEY`: OpenAI API access
- `TAVILY_API_KEY`: Tavily Search + Extract (web search and content retrieval)
- `SUPABASE_URL`, `SUPABASE_KEY`: City/topic config + report storage
- `TOGETHER_API_KEY`: Dynamic self-information scoring for context compression
- `GLAMA_API_KEY`: MCP for Google Calendar event creation

**Container-specific**:
- `NV_CITY`: City to run pipeline for (set by Dispatcher Lambda)
- `SQS_QUEUE_URL`: SQS queue URL for report-ready messages (triggers Email Lambda)
- `SQS_PIPELINE_DLQ_URL`: SQS dead letter queue URL for pipeline failure metadata

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
- Each tool adapter calls service functions from `utils/tools/utils/tavily.py` and returns a LangGraph `Command` for state updates
- Agent builds a LangGraph StateGraph with `call_model` and `tool_node` nodes; `recursion_limit` is applied at invoke-time via the config dict (not at compile-time)

**Error Handling**
- Classifier output parse failures → reject all sources (safe fallback)
- Per-topic failures are logged; container continues remaining topics then exits 1
- `save_report()` returning `None` is treated as a failure (exit 1)
- Pipeline failures are sent to the Pipeline DLQ (best-effort — never masks the original error)

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
docker run -e NV_CITY=toronto -e OPENAI_API_KEY=... -e TAVILY_API_KEY=... -e SUPABASE_URL=... -e SUPABASE_KEY=... -e TOGETHER_API_KEY=... -e GLAMA_API_KEY=... nv-local
```

**AWS (ECS Fargate)**:
- EventBridge Scheduler triggers Dispatcher Lambda weekly
- Dispatcher Lambda launches one Fargate task per supported city
- Each task runs `main.py` with `NV_CITY` set, executing all topics and saving to Supabase
- After all topics, task enqueues `{city, report_id}` to SQS; failures go to the Pipeline DLQ
- Email Lambda reads from `reports` table and sends via SES

**Logs**: Emitted to stdout/stderr; collected by CloudWatch in production.

## Important Known Issues / WIP

- Tavily Extract can fail on some domains (access restrictions, JS-heavy SPAs); `markdown.new` fallback handles most of these but is not 100% reliable

## Common Development Tasks

**Adding a new pipeline node**:
1. Create file in `pipelines/node/<node_name>.py`
2. Define node as a `RunnableSequence` or callable
3. Insert into `pipelines/nv_local.py:chain` in correct position
4. Update `utils/schemas/state.py:ChainData` if new state fields are needed
5. Document in `docs/ARCHITECTURE.md`

**Adding an agent tool**:
1. Create the tool adapter function in `utils/tools/` with the LangChain `@tool` decorator, then re-export it from `utils/tools/__init__.py`
2. If the tool needs an external service, add the business logic as a plain function in the appropriate service module (e.g., `utils/tools/utils/tavily.py`) or create a new one
3. Import the tool in the agent file (e.g., `from utils.tools import web_search`) and pass it to the agent constructor; it is automatically included in `ToolNode`

**Changing LLM model or config**:
1. Update `utils/llm/config.py:DEFAULT_LLM_CONFIG`
2. Note: All LLM factory functions reference this dict, so one change affects all calls

**Debugging a city pipeline failure**:
1. Run single city: `python main.py <city_name>`
2. Check error message in stdout/stderr
3. Likely causes: missing env vars (`OPENAI_API_KEY`, `TAVILY_API_KEY`), Tavily Extract failure on a domain, agent hitting `recursion_limit=40` before completing
4. Container mode: check ECS task logs in CloudWatch, verify `NV_CITY` is in `supported_cities` table
