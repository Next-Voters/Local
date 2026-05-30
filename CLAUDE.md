# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Next Voters Local** is a multi-agent AI research pipeline that discovers, researches, and summarizes municipal legislation across cities. It makes government information accessible to communities that lack time or resources to track local officials.

The system runs as a standalone CLI tool or Docker container, orchestrated by LangGraph-based agents. Each execution researches legislation for a given region and stores structured results (headers + bullets) in Supabase.

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
- **CLI entrypoint**: `main.py` → `pipelines/nv_local.py` (single-region, requires region argument validated against Supabase `regions`)
- **Container entrypoint**: `main.py` with `REGION` env var set (single-region, runs all topics, saves to Supabase `reports` table)

### Common Commands

```bash
# Compile check (catches syntax errors early)
python -m compileall -q .

# Run pipeline for a single region (requires OPENAI_API_KEY + TAVILY_API_KEY)
python main.py <region_name>

# Run pipeline for a region scoped to a specific topic
python main.py <region_name> -t <topic_name>

# Container mode (runs all topics for a region, saves to DB)
REGION=<region_name> python main.py
```

**Post-implementation verification**: After any code changes, always run `python -m compileall -q .` followed by `python main.py <region_name>` to confirm both compile-time and runtime correctness.

### Testing

There is no dedicated test suite. Quick validation:
- `python -m compileall -q .` to catch syntax errors
- Manual pipeline runs with test regions to verify data flow

## Architecture Overview

### Pipeline Structure

The pipeline is a **fixed, deterministic sequence** of nodes composed via LangGraph. This makes the execution path predictable and operational.

```
run_agent_team → note_taker → summary_writer
```

**Key design**: Each node is a thin `RunnableSequence` that transforms pipeline state (`ChainData` TypedDict).

### Deployment Model (AWS)

Each region runs as an independent **ECS Fargate task**:
- **EventBridge Scheduler** triggers weekly
- **Dispatcher Lambda** fans out — one ECS task per region
- Each Fargate task runs `main.py` with `REGION` env var, executing all topics sequentially
- Reports written to **Supabase Postgres** `reports` table
- After all topics complete, a `{region, report_id}` message is enqueued to **SQS**, triggering the **Email Lambda**
- If any topic or the SQS enqueue fails, failure metadata is sent to the **Pipeline DLQ** before exit 1
- **Email Lambda** (separate) reads reports and dispatches via **Amazon SES**

### Core Components

**Agents** (`agents/`):
- `researcher_agent.py`: ReAct subagent for issue-level legislation discovery, built with `create_agent` from `langchain.agents`. Terminates via `handoff` tool which writes summary to state and exits the graph.
- `lead_researcher_agent.py`: Supervisor agent that dispatches researchers per issue, validates sources, and synthesizes findings

**Pipeline Nodes** (`pipelines/node/`):
- `run_agent_team.py`: Runs a lead researcher agent per topic, filters sources, extracts `legislation_content` from content dicts
- `note_taker.py`: Compresses raw content into dense notes (single LLM call)
- `summary_writer.py`: Structured extraction of key legislative details (schema: `WriterOutput`)

**Utilities** (`utils/`):
- `llm/`: LLM factory (`get_llm()`, `get_structured_llm()`) with default config (gpt-5, temp=0, max_tokens=16384)
- `schemas/`:
  - `state.py`: `ChainData` TypedDict (pipeline state contract)
  - `pydantic.py`: Structured output schemas (e.g., `WriterOutput`)
- `report/`:
  - `storage.py`: Saves pipeline output to Supabase via a two-table upsert: parent `reports` row (per region+date) and child `report_headers` rows (per legislation item with topic, header, and bullets). Returns the `report_id` on success. Single function: `save_report(region, topic_name, result) → int | None`
- `content/`: Content processing and evaluation utilities
  - `compressor.py`: Context compression via `compress_text(text, rate, query)`. Uses blended self-information token pruning with head-truncation fallback. Called by `web_search` to compress extracted page content inline. Short content (<`MIN_CHARS_TO_COMPRESS` chars) bypasses compression.
  - `source_reliability.py`: Domain-level source reliability scoring and filtering — classifies URLs into government, legislative, news, other, or blocked tiers.

**Tools** (`tools/` — root level):
- `web_search.py`: Web search + inline content extraction (Tavily Search → Tavily Extract → compression) for legislation discovery
- `reflection.py`: Reflection tool for agent self-evaluation during ReAct loops
- `notes.py`: `note_taker` (records notes as SystemMessage with slug ID) and `delete_note` (removes via RemoveMessage)
- `handoff.py`: Researcher's exit tool — writes summary + sources to state and terminates the graph via `goto=END`
- `researcher_agent_tool.py`: Agent-as-tool wrapper that invokes the researcher subagent in an isolated context window
- `source_validator.py`: Parallel URL validation using structured mini-LLM calls
- `middleware.py`: `ReflectionMiddleware` for injecting reflection history before each LLM call
- `_helpers.py`: `ok()`/`err()` Command builders shared by all tools
- `services/tavily.py`, `services/extract.py`: Direct SDK wrappers for Tavily Search and Extract
- `supabase_client.py`: Loads supported regions and topics from Supabase
- `sqs_client.py`: SQS factory (`get_sqs_client()`) and message helpers (`enqueue_report()`, `enqueue_pipeline_failure()`)

**Configuration** (`config/`):
- `system_prompts/`: Prompt templates for agents and nodes
- `constants.py`: Pipeline-wide tuneable constants: `WEB_SEARCH_PER_URL_CHAR_CAP`, `COMPRESSION_RATE`, `MIN_CHARS_TO_COMPRESS`, `MAX_REFLECTION_ENTRIES`, `AGENT_RECURSION_LIMIT`, `MAX_RESEARCHER_INVOCATIONS`

### Data Flow Example

1. **Agent Team**: Lead researcher dispatches researcher subagents per issue. Each researcher's `web_search` tool calls Tavily Search, then Tavily Extract + compression inline — the researcher reads actual page content and produces an informed summary. Content dicts (`{"url", "content"}`) flow through state to `run_agent_team`, which extracts `legislation_content`.
2. **Note Taker**: LLM summarizes all content blocks into dense notes
3. **Summary Writer**: LLM extracts structured data (header + bullets per item) → `WriterOutput`
4. **Report Storage** (container mode): Upserts parent `reports` row (region+date), then `report_headers` rows (one per legislation item with topic, header, bullets). Returns `report_id`.
5. **SQS Notification** (container mode): Enqueues `{region, report_id}` to SQS so the Email Lambda can send the report. If any step failed, sends failure metadata to the Pipeline DLQ.

### Key Design Decisions

**Fixed pipeline over dynamic routing**
- Nodes execute in fixed order, making behavior predictable and debuggable
- Changes to pipeline structure happen at `pipelines/nv_local.py:chain`

**ReAct agents only for tool-use**
- Legislation discovery uses ReAct (multi-turn reasoning with tools)
- Note-taking and summary-writing are single-shot LLM transforms (simpler, cheaper)

**Source filtering in agent prompt**
- Source filtering is handled by the legislation finder agent's system prompt, which includes a classification table for accepting/rejecting sources based on type (government sites, legislative databases, factual news vs. opinion, blogs, aggregators)

**Inline content extraction in web_search**
- `web_search` calls Tavily Extract + `compress_text()` inline after each search, giving the researcher agent actual page content in its context window
- Each URL's raw content is capped at `WEB_SEARCH_PER_URL_CHAR_CAP` (30K chars) before compression to prevent context overflow
- At `COMPRESSION_RATE=0.4`, each URL yields ~12K chars of compressed content
- Content dicts (`{"url", "content"}`) accumulate in state via `operator.add` and are extracted into `legislation_content` by `run_agent_team`
- Short content (<`MIN_CHARS_TO_COMPRESS=1_000` chars) bypasses compression entirely

**Direct SDK calls for external services**
- Tavily search functions live in `tools/services/tavily.py` as direct SDK calls; tool adapters in `tools/` wrap them for LangGraph
- Tool adapters live in `tools/` with re-exports via `__init__.py`; agents import them rather than defining tools inline

**Rate limiting: bounded agent iterations**
- Pipeline nodes pass `AGENT_RECURSION_LIMIT=40` (from `config/constants.py`) at `ainvoke()` time via the `config` dict, preventing unbounded tool call loops that caused 429 Too Many Requests errors
- System prompts include explicit "Exit Criteria" sections with measurable stopping conditions
- Together these reduce LLM request volume ~40% while maintaining research quality

**Single-region Fargate tasks**
- Each ECS Fargate task runs ONE region (all topics sequentially)
- `REGION` env var is validated against `regions` before any API calls
- Each topic result is saved to DB immediately after pipeline completion
- After all topics, enqueues `{region, report_id}` to SQS for the Email Lambda
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
- `SUPABASE_URL`, `SUPABASE_KEY`: Region/topic config + report storage
- `TOGETHER_API_KEY`: Dynamic self-information scoring for context compression

**Container-specific**:
- `REGION`: Region to run pipeline for (set by Dispatcher Lambda)
- `SQS_QUEUE_URL`: SQS queue URL for report-ready messages (triggers Email Lambda)
- `SQS_PIPELINE_DLQ_URL`: SQS dead letter queue URL for pipeline failure metadata

## Common Patterns

**State Passing**
- Pipeline state is a `ChainData` TypedDict. Each node receives it as input, modifies relevant fields, and returns it.
- Example: `legislation_finder_node` receives `{"region": str, "topic": str}`, returns `{"region": str, "topic": str, "legislation_sources": list[str], ...}`

**LLM Calls**
- Structured output: use `get_structured_llm(OutputSchema)` → returns a Runnable that enforces schema
- Unstructured: use `get_llm()` → invoke with list of messages

**Agents**
- Built with `create_agent` from `langchain.agents` (see `agents/researcher_agent.py` for pattern)
- Tools live in `tools/` and are imported directly; agents compose their tool list at build time (e.g., `from tools import web_search, reflection_tool`)
- Each tool adapter calls service functions from `tools/services/tavily.py` and returns a LangGraph `Command` for state updates
- `ReflectionMiddleware` in `tools/middleware.py` injects reflection history before each LLM call; add it to the `middleware` list when building agents that use `reflection_tool`
- The agent-as-tool pattern (`tools/researcher_agent_tool.py`) wraps a subagent invocation as a tool, giving it an isolated context window
- `response_format` on `create_agent` enforces structured output schemas (e.g., `LeadResearcherOutput`); the researcher uses a `handoff` tool instead of `response_format` for its exit
- `recursion_limit` is applied at invoke-time via the config dict; `MAX_RESEARCHER_INVOCATIONS` limits subagent dispatch at the tool level via `InjectedState`

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
- **Linting**: Ruff linter + formatter, configured in `pyproject.toml`. Run `ruff check --fix . && ruff format .` before committing, or rely on the pre-commit hook

## Deployment

**Local**: `python main.py <region>`

**Docker**:
```bash
docker build -f docker/Dockerfile -t nv-local .
docker run -e REGION=toronto -e OPENAI_API_KEY=... -e TAVILY_API_KEY=... -e SUPABASE_URL=... -e SUPABASE_KEY=... -e TOGETHER_API_KEY=... nv-local
```

**AWS (ECS Fargate)**:
- EventBridge Scheduler triggers Dispatcher Lambda weekly
- Dispatcher Lambda launches one Fargate task per supported region
- Each task runs `main.py` with `REGION` set, executing all topics and saving to Supabase
- After all topics, task enqueues `{region, report_id}` to SQS; failures go to the Pipeline DLQ
- Email Lambda reads from `reports` table and sends via SES

**Logs**: Emitted to stdout/stderr; collected by CloudWatch in production.

## Important Known Issues / WIP

- Tavily Extract can fail on some domains (access restrictions, JS-heavy SPAs); when extraction fails for a URL, `web_search` returns an empty content string and the researcher works from search snippets only

## Common Development Tasks

**Adding a new pipeline node**:
1. Create file in `pipelines/node/<node_name>.py`
2. Define node as a `RunnableSequence` or callable
3. Insert into `pipelines/nv_local.py:chain` in correct position
4. Update `utils/schemas/state.py:ChainData` if new state fields are needed
5. Document in `docs/ARCHITECTURE.md`

**Adding an agent tool**:
1. Create the tool function in `tools/` with the LangChain `@tool` decorator; return a `Command` using `ok()`/`err()` from `tools/_helpers.py`
2. If the tool needs an external service, add the business logic in `tools/services/` (e.g., `tools/services/tavily.py`)
3. Import the tool in the agent file (e.g., `from tools import web_search`) and include it in the `tools` list when calling `create_agent`

**Changing LLM model or config**:
1. Update `utils/llm/config.py:DEFAULT_LLM_CONFIG`
2. Note: All LLM factory functions reference this dict, so one change affects all calls

**Debugging a region pipeline failure**:
1. Run single region: `python main.py <region_name>`
2. Check error message in stdout/stderr
3. Likely causes: missing env vars (`OPENAI_API_KEY`, `TAVILY_API_KEY`), Tavily Extract failure on a domain, agent hitting `recursion_limit=40` before completing
4. Container mode: check ECS task logs in CloudWatch, verify `REGION` is in `regions` table
