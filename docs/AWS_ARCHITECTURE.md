# AWS System Design

High-level architecture for the City Agent email pipeline. Reports are generated weekly per city, queued via SQS, and emailed to subscribers via SES.

```mermaid
flowchart LR
    %% Trigger layer
    EB["EventBridge Scheduler<br/>weekly cron"]
    DL["Dispatcher Lambda<br/>fan-out per city"]

    %% Compute layer
    subgraph VPC["AWS VPC"]
        ECS["ECS Fargate<br/>1 task per city"]
    end
    EXT["External APIs<br/>LLM / scraping"]

    %% Messaging layer
    SQS["SQS<br/>report-ready queue"]
    DLQ[("SQS DLQ<br/>failed messages")]

    %% Delivery layer
    EML["Email Lambda<br/>concurrency = 10"]
    SES["Amazon SES"]
    USERS["User Inboxes"]

    %% Data layer
    DB[("Supabase Postgres<br/>cities, subscribers,<br/>reports, bullets, send_log")]

    %% Main flow
    EB --> DL
    DL --> ECS
    ECS <-.->|"Internet Gateway Access"| EXT
    ECS -->|"write report<br/>+ bullets"| DB
    ECS -->|"enqueue<br/>{city_id, report_id}"| SQS
    SQS --> EML
    EML -->|"read report<br/>write send_log"| DB
    EML --> SES
    SES --> USERS

    %% Side flows
    DL -.->|read cities| DB
    SQS -.->|after N retries| DLQ

    classDef aws fill:#FF9900,stroke:#232F3E,stroke-width:2px,color:#fff
    classDef ext fill:#4A90E2,stroke:#1F3A5F,stroke-width:2px,color:#fff
    classDef db fill:#1F6B47,stroke:#0D3322,stroke-width:2px,color:#fff
    classDef queue fill:#CC2264,stroke:#5C0F2E,stroke-width:2px,color:#fff
    classDef user fill:#7B68EE,stroke:#3F2E8C,stroke-width:2px,color:#fff

    class EB,DL,ECS,EML,SES aws
    class EXT ext
    class DB db
    class SQS,DLQ queue
    class USERS user
    style VPC fill:#1F3A5F,stroke:#0D1F33,stroke-width:2px,color:#fff

    %% Bold the Internet Gateway Access dotted arrow (link index 2)
    linkStyle 2 stroke-width:3px,stroke:#fff
```

## Flow Summary

1. **EventBridge** triggers the **Dispatcher Lambda** on a weekly cron.
2. **Dispatcher Lambda** reads the active cities from **Supabase** and fans out one **Fargate** task per city.
3. Each **Fargate task** calls external APIs (LLM, scraping) to generate report content, writes the report and its bullets to **Supabase**, then enqueues a message to **SQS** containing `{city_id, report_id}` and exits.
4. **SQS** holds the message. AWS-managed pollers invoke the **Email Lambda** with batches of messages, respecting the Lambda's reserved concurrency cap of 10 to protect SES rate limits.
5. **Email Lambda** reads the report and bullets from Supabase, queries subscribers for the city, renders the email, sends via **SES**, and writes to `send_log` for idempotency.
6. Failed messages are retried automatically by SQS. After N failures, they land in the **DLQ** for investigation.
