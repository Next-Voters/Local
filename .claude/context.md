# AI Politician Accountability — System Design

## Overview
This design describes an AI agent system that collects representative data (via OpenNorth), runs deep research agents to gather evidence about a politician, and produces age‑appropriate summaries for adults and children.

## Data Source
- Primary: OpenNorth representatives API (by lat/long).

Example request (Python module provides lat/long):

```
https://represent.opennorth.ca/representatives/house-of-commons/?point=45.524%2C-73.596
```

Example (trimmed) response:

```json
{
  "objects": [
    {
      "name": "Rachel Bendayan",
      "district_name": "Outremont",
      "elected_office": "MP",
      "party_name": "Liberal",
      "email": "Rachel.Bendayan@parl.gc.ca",
      "url": "https://www.ourcommons.ca/Members/en/rachel-bendayan(88567)",
      "photo_url": "https://.../BendayanRachel_Lib.jpg",
      "offices": [ /* ... */ ]
    }
  ],
  "meta": { "total_count": 1 }
}
```

## High-level Flow
1. User Location Module (Python) provides lat/long.
2. OpenNorth API Fetcher retrieves representative(s) for that point.
3. Manager / Orchestrator enqueues and dispatches research tasks to multiple agents.
4. Agents (parallel): political activities, personal controversies, voting & policy (and optionally media coverage).
5. Supervisor collects raw HTML and metadata from agent results and stores the source.
6. Summarizer LLM ingests collected HTML and creates two formats: Adult Summary (semi-formal) and Kid Summary (age-appropriate slang/fine-tuned).
7. Summaries are exposed through simple UIs (Adult UI, Kid UI).

## Components & Short Descriptors
- User Location Module — obtains user coordinates (Python), feeds the OpenNorth request.
- OpenNorth API Fetcher — queries the OpenNorth endpoint for representatives by point.
- Task Queue — queues research jobs for the manager to process.
- Manager / Orchestrator — dispatches jobs to specialized agents and tracks progress.
- Agent: Political Activities — finds public political actions (bills, motions, public statements).
- Agent: Controversies — searches for personal controversies, ethics reports, news items.
- Agent: Voting & Policy — collects voting records, public positions, and policy stances.
- (Optional) Agent: Media Coverage — aggregates recent coverage and sentiment.
- Supervisor — aggregates raw HTML and metadata returned by agents; stores source pages.
- Raw HTML Store — blob storage for source pages (keeps provenance).
- Summarizer LLM — model tuned to summarize HTML into concise prose.
- Adult Summary — semi-formal, contextual summary for adults.
- Kid Summary — simplified, engaging summary using age-appropriate language (requires fine-tuning).
- Adult UI / Kid UI — presentation layers for consumers.

## Notes & Scope
- This design intentionally excludes infrastructure concerns (monitoring, auth, schedulers, vector DBs) to keep scope focused on the research pipeline and summarization.
- The system preserves source HTML for auditing and provenance.
- The Kid Summary requires a fine-tuning pipeline (not included in current scope) to ensure cultural relevance and safety.

## Next Steps (suggested)
- Add a minimal Python fetcher and queue prototype to demonstrate end-to-end flow.
- Wire a basic Supervisor that saves HTML to `/data/` and passes it to a summarizer stub.
- Create simple static pages for Adult UI and Kid UI to display outputs.
