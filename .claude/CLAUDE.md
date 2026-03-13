# 📋 Project Configuration — Next Voters Local

**Next Voters Local** is a multi-agent system that intelligently investigates legislation and provides an easy to understand summary.

---

## 🚨 CRITICAL RULES

- **Do not over-engineer.** Keep implementations simple and direct. Resist adding abstraction layers, patterns, or indirection that aren't strictly necessary.
- **Minimal agency principle.** Only use true ReAct agents where autonomous decision-making is required (search/evaluate/retry loops, code debugging). Everything else is a single LLM call or pure deterministic code. Never add agency to a step that has no real decisions.
- **No supervisor pattern.** The pipeline is sequential; each agent depends on the previous agent's output. A supervisor would be a wasted LLM call since routing is always the same.
- **No planner-executor pattern.** Same reasoning — the plan is identical every run. Use a static LangGraph DAG.
- **Judge isolation is non-negotiable.** The Judge LLM call must never see the real politician name, never see graph state (retry count, etc.), and never have tools or memory. Its effectiveness comes entirely from its narrow, isolated scope.
- **Rhetoric Neutralizer must never guess politician identity.** Hard constraint — anonymization happens upstream via the Redactor before the Neutralizer ever receives input.
- **Always use `model=` parameter (not `llm=`)** when calling `create_react_agent` in the current LangGraph version (1.0.10).
- **Never use `langgraph-supervisor`** — it has been removed from requirements and is not part of this architecture.
- **Never waste time praising me for good actions or trying to inflate my ego. Stay true to simply helping me engineer a world-class systems.**
---

## 🎯 PROJECT CONTEXT

### Product Goal
Targets Canadian politics initially. Scrapes legislation data, finds politician positions on that legislation, neutralizes political rhetoric and bias, and presents factual information to end users.

### Initial Data Source
- **OpenNorth API** — for Canadian representative data

### Technology Stack
| Layer | Technology |
|---|---|
| Orchestration | LangGraph (v1.0.10), static `StateGraph` DAG |
| LLM calls | `langchain-openai` (v1.1.11), OpenAI models |
| Web search | Tavily (Agent 1) |
| Scraping / REPL | Agent 2 self-generated Python code with debugging tool |
| Anonymization | NER-based (spaCy or equivalent), pure code |
| Vector DB | TBD — downstream from Research Writer |
| RAG Chatbot | Downstream consumer of Vector DB, separate from pipeline |
| Config | `python-dotenv` |

### Architecture Philosophy
Sequential pipeline. No supervisor. No dynamic routing. Linear LangGraph DAG:

```
Agent 1 (ReAct) → Agent 2 (ReAct) → Agent 3 (ReAct)
  → Redactor (code) → Rhetoric Neutralizer (LLM call)
  → Judge (LLM call) → Research Writer (LLM call)
  → Vector DB Write (code) → Citation Validation (code)
  → Presentation LLM (call) → Output
```

---

## 🔧 DEVELOPMENT PATTERNS

### Component Classification
Always classify new components before building:

| Type | Use When | Examples in This Project |
|---|---|---|
| **ReAct Agent** | Unpredictable targets, retry loops, code self-correction, relevance judgment | Agents 1, 2, 3 |
| **Single LLM Call** | Fixed input → structured output, no tools, no iteration | Rhetoric Neutralizer, Judge, Research Writer, Presentation LLM |
| **Pure Code** | Deterministic, rule-based, no language understanding needed | Redactor, Vector DB Write, Citation Validation |

### File Organization
```
/
├── main.py                  # LangGraph StateGraph — linear DAG wiring
├── requirements.txt         # Dependencies (no langgraph-supervisor)
├── .env                     # API keys (python-dotenv)
├── diagrams/
│   └── ai-politician-accountability.mmd   # Mermaid diagram
├── utils/
│   ├── agent.py             # Factory functions: build_agent_1(llm), build_agent_2(llm), build_agent_3(llm)
│   └── tools.py             # Tool implementations for agents
└── CLAUDE.md                # This file
```

### Coding Standards
- Factory functions for agent construction: `build_agent_N(llm)` pattern
- `create_react_agent(model=llm, tools=[...])` — use `model=` keyword
- Structured JSON output for all LLM calls (Rhetoric Neutralizer, Judge, Research Writer)
- All LLM calls have explicit system prompts with hard constraints stated upfront
- Stubs first, real implementations second — never block pipeline testing on incomplete tools

### Known Gotchas
- `create_react_agent` uses `model=` not `llm=` in LangGraph 1.0.10
- `langgraph-supervisor` is not installed and must not be introduced

---

## 🤖 PIPELINE COMPONENTS — FULL SPEC

### ReAct Agents

#### Agent 1: Legislation Finder
- **Role:** Searches web for legislation, validates source reliability, retries with different queries if results are poor
- **Returns:** URLs + bill metadata
- **Needs agency because:** Search targets are unpredictable; source reliability evaluation may require re-searching
- **Key tool:** Source Reliability Tool (see below)
- **Web search:** Tavily

#### Agent 2: Scraper Builder
- **Role:** Generates Python scraping code, executes via REPL, filters content by date (last 7 days)
- **Needs agency because:** Scrapes arbitrary URLs with unpredictable HTML structures; LLM-generated code may fail and needs self-correction
- **Key tool:** Debugging tool — lets Agent 2 inspect and fix its own code

#### Agent 3: Politician Position Finder
- **Role:** Finds politician statements, press releases, floor speeches, vote records across multiple source types
- **Needs agency because:** Makes relevance judgments about results, decides whether to keep searching

### Single LLM Calls

#### Rhetoric Neutralizer
- **Input:** Anonymized politician statements (real names already stripped by Redactor)
- **Output:** Structured JSON — extracted claims with source citations, rhetorical device classifications
- **Hard constraint:** Must never attempt to guess politician identity
- **Debiasing:** Two-pass self-debiasing (Layer 3) — based on Gallegos et al., 2024 (arXiv:2402.01981)

#### Judge
- **Input:** Rhetoric Neutralizer output (anonymized — no real names)
- **Model:** Different OpenAI model than Rhetoric Neutralizer (same company, different model — for independence)
- **Isolation constraints:** Never sees real politician name. Never sees graph state (retry count, pipeline position, etc.)
- **Evaluates 4 criteria:**
  - `criterion_0`: Identity Inference Prohibition — HARD CONSTRAINT
  - `criterion_1`: Grounding Violation
  - `criterion_2`: Tonal Bias
  - `criterion_3`: Unsupported Inference
- **Output:** Structured JSON verdict — `pass`/`fail` per criterion + `revision_instructions`
- **Retry logic:**
  - Soft fail → send feedback to Rhetoric Neutralizer, max 2 retries
  - Identity inference fail → route back to Redactor for stronger anonymization
  - Retries exhausted → quarantine with `confidence: low`
- **Theoretical basis:** Phute et al., 2023 (arXiv:2308.07308) — specifies judge as single LLM call, not agent

#### Research Writer
- **Input:** All upstream data (legislation, politician positions, neutralized statements)
- **Output:** Structured research notes, cross-referenced sources

#### Presentation LLM
- **Input:** Research Writer output
- **Output:** User-facing factual summary

### Pure Code Steps

#### Redactor
- **Method:** NER-based name removal — strips politician names, titles, committee affiliations
- **Replaces with:** `Legislator A`, `Legislator B`, `Legislator C` (consistent within a document)
- **Runs before:** Rhetoric Neutralizer (so it never sees real names)

#### Vector DB Write
- **Input:** Research Writer output embeddings
- **Action:** Publishes to Vector DB for RAG Chatbot consumption

#### Citation Validation (Layer 5 debiasing)
- **Method:** Checks whether quoted text actually exists in source documents

---

## 🛠️ SOURCE RELIABILITY TOOL — SPEC

A tool inside Agent 1 (not a separate graph node). Ensures only trustworthy, authoritative sources pass through.

### Two-Layer Design

**Layer 1: Domain Heuristic Check (deterministic code)**
- ✅ Pass: `.gov`, `.gc.ca`, known legislative platforms (Legistar, eScribe, Granicus)
- ❌ Fail: social media, blogs, opinion sites
- ❓ Uncertain: goes to Layer 2

**Layer 2: LLM Source Evaluation (single LLM call — not an agent)**
- For uncertain URLs only
- Classifies as: `official` | `likely_official` | `news` | `unreliable` | `unknown`
- Only `official` and `likely_official` pass through

### Open Question
**News article policy:** Should CBC, local newspapers be allowed as secondary sources, or excluded entirely?
- **Allow as secondary:** Provides corroboration but introduces editorial bias risk
- **Exclude entirely:** Cleaner bias story but loses corroborating evidence

---

## 🛡️ DEBIASING STRATEGY — LAYERED DEFENSE IN DEPTH

| Layer | Where | Method |
|---|---|---|
| **Layer 1** | Input (Redactor) | Entity anonymization — strip politician names before Rhetoric Neutralizer |
| **Layer 2** | LLM call design | Structured output with mandatory source citations |
| **Layer 3** | Intra-call | Self-debiasing via reprompting (two-pass) — Gallegos et al., 2024 (arXiv:2402.01981) |
| **Layer 4** | Post-call | LLM-as-Judge bias screen — Phute et al., 2023 (arXiv:2308.07308) |
| **Layer 5** | Programmatic | Citation validation — code checks quoted text exists in source |

---

## 🐝 AGENT COORDINATION

This project uses a **static sequential DAG** — each node runs once, in order, passing output to the next. There is no dynamic task distribution, no parallel agent execution, and no routing decisions at runtime. If parallelism is ever introduced (e.g., Agent 3 searching multiple source types simultaneously), implement it as LangGraph parallel branches — not via a supervisor or swarm coordinator.

---

## 🧠 MEMORY MANAGEMENT

- **Agents are stateless between pipeline runs.** No cross-run memory.
- **Within a run:** LangGraph `StateGraph` carries a shared state dict through all nodes. Each node reads from and writes to this shared state.
- **Judge is deliberately context-blind** — it receives only the anonymized output it needs to evaluate, no history, no retry count, no pipeline metadata. This is an intentional design constraint.
- **Vector DB** is the only persistence layer — Research Writer output is embedded and stored for the RAG Chatbot to query.

---

## 🔒 SECURITY & COMPLIANCE

- **Identity protection:** Politician names must be stripped before any LLM call that performs rhetoric or bias analysis — this is both a privacy design and a debiasing requirement
- **Judge isolation:** The Judge must be stateless and context-blind by design — accessing graph state would allow it to reason about consequences of its verdict, introducing bias
- **Source authority:** Only `official` and `likely_official` sources pass the Source Reliability Tool — this prevents partisan or unreliable sources from polluting the pipeline
- **Quarantine path:** Outputs that fail Judge review after max retries are quarantined with `confidence: low` rather than dropped silently or surfaced to users

---

## 🚀 DEPLOYMENT & CI/CD

Local development only. `.env` via `python-dotenv` for API key management.

---

## 📚 KEY REFERENCES

- Gallegos et al., 2024 — *Bias and Fairness in Large Language Models: A Survey* (arXiv:2402.01981) — informs Layer 3 self-debiasing
- Phute et al., 2023 — *LLM Self Defense* (arXiv:2308.07308) — informs Judge design: single LLM call, no tools, no memory, narrow scope