# Software Infrastructure Diagrams

This document contains key infrastructure diagrams for the Next Voters project.

## Azure Infrastructure CI/CD Pipeline

This diagram illustrates the continuous integration and deployment pipeline using GitHub Actions and Azure Container Apps. It shows the flow from code push to container execution with monitoring.

```mermaid
flowchart TD
    subgraph GH["GitHub Actions"]
        A[Push code to repo]
        B[Build Docker image]
    end
    subgraph Azure["Azure Cloud"]
        C[Azure Container Registry]
        D[Azure Container Apps Environment]
        E[Azure Container Apps Job]
        F[Schedule Trigger\ncron in UTC]
        G[Azure Key Vault]
        H[Managed Identity]
        I[Azure Monitor / Log Analytics]
    end
    subgraph Execution["Single Container Execution"]
        J[Container starts]
        K[Worker entrypoint]
        L[Multi-city pipeline runs\none after another]
        M[Container exits]
    end

    A --> B
    B --> C
    C --> E
    G --> E
    H --> E
    F --> E
    D --> E
    E --> J
    J --> K
    K --> L
    L --> M
    M --> I
    K --> I

    style GH fill:#1e3a5f,stroke:#60a5fa,stroke-width:1.5px,color:#bfdbfe
    style Azure fill:#3b0764,stroke:#a78bfa,stroke-width:1.5px,color:#ddd6fe
    style Execution fill:#134e4a,stroke:#2dd4bf,stroke-width:1.5px,color:#99f6e4
```

## Supabase Database Schema

Entity-relationship diagram showing the database schema for the Next Voters application. It includes tables for users, cities, political figures, legislation, tasks, and their relationships.

```mermaid
erDiagram
    users ||--o{ user_profiles : has
    users ||--o{ cities : owns
    users ||--o{ tasks : runs
    
    user_profiles {
        uuid id PK
        uuid user_id FK
        string full_name
        string avatar_url
        timestamp updated_at
    }

    cities ||--o{ political_figures : contains
    cities ||--o{ legislation : contains
    cities ||--o{ reports : generates
    cities ||--o{ tasks : tracks
    
    cities {
        uuid id PK
        string name
        string state
        string country
        timestamp created_at
        uuid owner_id FK
    }

    political_figures ||--o{ political_commentary : makes
    political_figures ||--o{ social_media_posts : posts
    
    political_figures {
        uuid id PK
        uuid city_id FK
        string name
        string position
        string party
        string jurisdiction
        string source_url
    }

    political_commentary {
        uuid id PK
        uuid political_figure_id FK
        uuid city_id FK
        string source_url
        text comment
        float reliability_score
        timestamp created_at
    }

    social_media_posts {
        uuid id PK
        uuid political_figure_id FK
        string platform
        string tweet_id
        text text
        timestamp created_at
        jsonb engagement
    }

    legislation ||--o{ legislation_sources : references
    
    legislation {
        uuid id PK
        uuid city_id FK
        string title
        text summary
        text body
        timestamp created_at
        timestamp updated_at
    }

    legislation_sources {
        uuid id PK
        uuid legislation_id FK
        string url
        string organization
        float reliability_score
    }

    reports {
        uuid id PK
        uuid city_id FK
        string title
        text markdown_report
        text summary
        timestamp created_at
        timestamp updated_at
    }

    tasks {
        uuid id PK
        uuid city_id FK
        uuid user_id FK
        string status
        text result
        text error
        timestamp created_at
        timestamp updated_at
    }

    user_profiles ||--o{ cities : follows
```

## System Design: Legislation & Accountability Pipeline

This diagram depicts the sequential pipeline for legislation analysis and accountability, using LangGraph with three ReAct agents, single LLM calls, and pure code steps. It includes conditional retry logic and vector database integration.

```mermaid
graph TB
    %% Sequential Pipeline — Legislation & Accountability System
    %% Static LangGraph DAG with Conditional Retry Edge
    %% 3 ReAct Agents | 4 Single LLM Calls | 3 Pure Code Steps

    START([User Trigger]) --> AGENT1

    %% AGENT 1 — ReAct Agent
    AGENT1[Agent 1: Legislation Finder — ReAct]
    AGENT1 --> A1_TOOLS[Tools: Web Search, URL Fetcher, HTML Parser, Source Reliability]
    AGENT1 ==>|URLs + bill metadata| AGENT2

    %% AGENT 2 — ReAct Agent
    AGENT2[Agent 2: Scraper Builder — ReAct]
    AGENT2 --> A2_TOOLS[Tools: Code Generator, Python REPL, Date Filter, Debugger]
    AGENT2 ==>|raw legislation text + vote records| AGENT3

    %% AGENT 3 — ReAct Agent
    AGENT3[Agent 3: Politician Position Finder — ReAct]
    AGENT3 --> A3_TOOLS[Tools: Web Search, Press Release Scraper, Floor Speech Parser, Vote Record Matcher]
    AGENT3 ==>|raw politician statements| REDACTOR

    %% REDACTOR — pure code, no LLM
    REDACTOR([Redactor — Pure Code])
    REDACTOR ==>|anonymized statements + raw source| RHETORIC

    %% RHETORIC NEUTRALIZER — single LLM call, no tools
    RHETORIC{{Rhetoric Neutralizer — Single LLM Call}}
    RHETORIC ==>|structured neutral analysis| JUDGE

    %% JUDGE — single LLM call, stateless, no tools, no memory, different model
    JUDGE{{Judge — Single LLM Call, Different Model}}
    JUDGE -->|PASS| RESEARCH
    JUDGE -->|FAIL: soft criteria| RHETORIC
    JUDGE -->|FAIL: identity inference| REDACTOR
    JUDGE -->|retries exhausted| QUARANTINE([Quarantine — confidence: low])
    QUARANTINE -.-> RESEARCH

    %% RESEARCH WRITER — single LLM call, no tools
    RESEARCH{{Research Writer — Single LLM Call}}
    RESEARCH ==>|research notes| CITATION

    %% CITATION VALIDATION — pure code, no LLM
    CITATION([Citation Validation — Pure Code])
    CITATION ==>|validated notes| VECTORDB_WRITE

    %% VECTOR DB WRITE — pure code, no LLM
    VECTORDB_WRITE([Vector DB Write — Pure Code])
    VECTORDB_WRITE -->|publish embeddings| VECTOR_DB[(Vector Knowledge DB)]
    VECTORDB_WRITE ==>|validated research notes| PRESENTATION

    %% PRESENTATION LLM — single LLM call
    PRESENTATION{{Presentation LLM — Single LLM Call}}
    PRESENTATION --> OUTPUT([Final User Output])

    %% RAG — downstream consumer
    VECTOR_DB -.->|retrieval| RAG[RAG Chatbot]

    %% LEGEND
    %% [Square] = ReAct Agent (autonomous tool-use loop)
    %% {{Diamond}} = Single LLM Call (no tools, no agency)
    %% ([Rounded]) = Pure Code Step (no LLM at all)
    %% ==> thick arrow = chain dependency
    %% --> solid arrow = data flow / tool access
    %% -.-> dashed = conditional / async path
    %% Judge criteria: 0) Identity inference prohibition 1) Grounding 2) Tonal bias 3) Unsupported inference
    %% Judge retry: max 2 retries, then quarantine
    %% Redactor: NER-based name removal, title stripping, replaces with Legislator A/B/C
```