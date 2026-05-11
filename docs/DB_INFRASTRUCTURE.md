# Database Infrastructure

The Supabase database is organized into four functional groups: pipeline tables (core to the NV Local research pipeline), platform tables (admin, chat, and region voting), LangGraph persistence tables (managed by the LangGraph framework), and migration tracking. All tables have RLS enabled.

---

## Pipeline Tables

These tables power the NV Local research pipeline — city/topic configuration, subscriber management, and report storage.

### regions

| Column | Type | Notes |
| --- | --- | --- |
| `region` | `text` | Primary key; canonical region label. |

Lookup table constraining subscriptions and reports to the vetted list of launch markets.

### supported_topics

| Column | Type | Notes |
| --- | --- | --- |
| `topic_id` | `integer` | Identity primary key (BY DEFAULT). |
| `topic_name` | `text` | Unique canonical label (e.g., `immigration`, `civil rights`, `economy`). |
| `description` | `text` | Short explanation of what the topic covers. |

New topics must be inserted here first so that `subscription_topics` and `reports` can reference their IDs.

### subscriptions

| Column | Type | Notes |
| --- | --- | --- |
| `contact` | `text` | Primary key; subscriber email or handle. |
| `region` | `text` | Nullable; foreign key → `regions.region`. |
| `stripe_customer_id` | `text` | Nullable; Stripe customer identifier. |
| `stripe_subscription_id` | `text` | Nullable; Stripe subscription identifier. |
| `stripe_status` | `text` | Nullable; current Stripe subscription status. |
| `stripe_period_end` | `timestamptz` | Nullable; end of the current billing period. |
| `referral_code` | `text` | Nullable, unique; subscriber's referral code. |
| `tier` | `text` | Nullable; subscription tier. CHECK: `'pro'` or `'free'`. |

Each subscription holds a unique contact identifier and optionally references a region. Stripe billing fields track subscription state. Topics are managed through the `subscription_topics` junction table.

### subscription_topics (Junction Table)

| Column | Type | Notes |
| --- | --- | --- |
| `subscription_id` | `text` | Foreign key → `subscriptions.contact`. |
| `topic_id` | `integer` | Foreign key → `supported_topics.topic_id`. |

Composite primary key `(subscription_id, topic_id)`. Implements the many-to-many relationship between subscriptions and topics.

### reports

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `bigint` | Identity primary key (ALWAYS GENERATED). |
| `region` | `text` | Foreign key → `regions.region`. |
| `report_date` | `date` | Date the report covers; defaults to `CURRENT_DATE`. |

Parent record for a region's daily pipeline run. A unique constraint on `(region, report_date)` enforces one report per region per day; re-runs upsert over the existing row. Individual legislation items are stored in `report_headers`.

### report_headers

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `bigint` | Identity primary key (ALWAYS GENERATED). |
| `report_id` | `bigint` | Foreign key → `reports.id`. ON DELETE CASCADE. |
| `topic_id` | `integer` | Foreign key → `supported_topics.topic_id`. ON DELETE CASCADE. |
| `header` | `text` | Legislation item headline. |
| `bullets` | `jsonb` | Array of bullet point strings. Defaults to `'[]'::jsonb`. |

Each row stores one legislation header with its bullet points. A unique constraint on `(report_id, topic_id, header)` prevents duplicate headers for the same topic within a report; re-runs upsert over existing rows. Indexed on `report_id` for join performance.

---

## Platform Tables

These tables support the Next Voters web platform — admin management, chat tracking, and community-driven city expansion requests.

### admin_table

| Column | Type | Notes |
| --- | --- | --- |
| `email` | `text` | Primary key; admin email address. |
| `name` | `text` | Admin display name. |

### user_admin_requests

| Column | Type | Notes |
| --- | --- | --- |
| `email` | `text` | Primary key; requester email address. |
| `name` | `text` | Requester display name. |

Holds pending requests for admin access. Approved entries are promoted to `admin_table`.

### chat_count

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `bigint` | Identity primary key (BY DEFAULT). |
| `responses` | `bigint` | Number of chat responses served. |
| `requests` | `bigint` | Nullable; number of chat requests received. |

Tracks aggregate chat usage metrics.

### region_requests

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `integer` | Serial primary key. |
| `region` | `text` | Unique; the requested region name. |
| `vote_count` | `integer` | Current vote tally; defaults to `0`. |
| `threshold` | `integer` | Votes required for approval; defaults to `25`. |
| `status` | `text` | CHECK: `'pending'`, `'approved'`, or `'rejected'`; defaults to `'pending'`. |
| `created_at` | `timestamptz` | Row creation timestamp; defaults to `now()`. |

Community-driven region expansion: users vote for regions they want covered. When `vote_count` reaches `threshold`, the request can be approved and the region added to `regions`.

### region_votes

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `integer` | Serial primary key. |
| `request_id` | `integer` | Foreign key → `region_requests.id`. |
| `voter_email` | `text` | Email of the voter. |
| `referral_code` | `text` | Nullable; referral code used when voting. |
| `created_at` | `timestamptz` | Vote timestamp; defaults to `now()`. |

Individual votes cast for a region request.

---

## LangGraph Persistence Tables

These tables are managed by the LangGraph framework and store agent execution state. They are not directly queried by application code.

| Table | Primary Key | Purpose |
| --- | --- | --- |
| `assistant` | `assistant_id` (uuid) | Registered assistant definitions (graph_id, config, metadata, version). |
| `assistant_versions` | `(assistant_id, version)` | Version history for assistant configurations. FK → `assistant`. |
| `thread` | `thread_id` (uuid) | Conversation threads with status, config, values, and interrupts. |
| `thread_ttl` | `id` (uuid) | TTL policies for threads (strategy, ttl_minutes, computed expires_at). FK → `thread`. |
| `run` | `run_id` (uuid) | Individual execution runs tied to a thread and assistant. |
| `checkpoints` | `(thread_id, checkpoint_id, checkpoint_ns)` | Graph state snapshots at each step. |
| `checkpoint_blobs` | `(thread_id, channel, version, checkpoint_ns)` | Binary blobs for checkpoint channel data. |
| `checkpoint_writes` | `(thread_id, checkpoint_id, task_id, idx, checkpoint_ns)` | Pending writes for checkpoint channels. |
| `cron` | `cron_id` (uuid) | Scheduled recurring runs (schedule, payload, enabled flag). FK → `assistant`, `thread`. |
| `store` | `(prefix, key)` | Key-value store with optional TTL for cross-thread persistence. |

---

## Schema Migrations

| Column | Type | Notes |
| --- | --- | --- |
| `version` | `bigint` | Primary key; migration version number. |
| `dirty` | `boolean` | Whether this migration is in a dirty (incomplete) state. |

Standard migration tracking table used by the migration framework.

---

## Entity Relationships

```mermaid
erDiagram
    regions ||--o{ subscriptions : "region"
    regions ||--o{ reports : "region"
    reports ||--o{ report_headers : "report_id"
    supported_topics ||--o{ subscription_topics : "topic_id"
    supported_topics ||--o{ report_headers : "topic_id"
    subscriptions ||--o{ subscription_topics : "contact"
    region_requests ||--o{ region_votes : "request_id"
    assistant ||--o{ assistant_versions : "assistant_id"
    assistant ||--o{ cron : "assistant_id"
    thread ||--o{ thread_ttl : "thread_id"
    thread ||--o{ cron : "thread_id"
```

Key relationships:
- `regions` supplies region references for `subscriptions` and `reports` (one-to-many).
- `reports` → `report_headers` (one-to-many; each report has multiple headers across topics).
- `supported_topics` is referenced by `subscription_topics` (subscriber preferences) and `report_headers` (pipeline output).
- `subscriptions` ↔ `supported_topics` linked through `subscription_topics` (many-to-many).
- `region_requests` ↔ `region_votes` (one-to-many; each request collects votes).
- LangGraph tables: `assistant` → `assistant_versions` and `cron`; `thread` → `thread_ttl` and `cron`.

---

## Code Integration

Pipeline tables are queried via two modules:

**`utils/supabase_client.py`**:
- `get_supabase_client()` → `Client` — creates a Supabase client from `SUPABASE_URL` and `SUPABASE_KEY` env vars
- `get_supported_regions_from_db()` → `list[str]` — queries `regions` ordered alphabetically
- `get_supported_topics()` → `list[str]` — queries `supported_topics.topic_name` ordered alphabetically

**`utils/report/storage.py`**:
- `_get_topic_id(topic_name)` → `int | None` — resolves a topic name to its integer ID via `supported_topics` (cached)
- `save_report(region, topic_name, result)` → `int | None` — upserts a `reports` row on `(region, report_date)`, then upserts `report_headers` rows per legislation item on `(report_id, topic_id, header)`. Returns the `report_id` on success, `None` on failure.

---

## Operational Guidance

- **Seed lookup tables first**: ensure all topics and regions exist in their respective lookup tables before creating subscriptions or junction table entries.
- **Insert topics before linking**: when adding a new topic, insert it into `supported_topics`, then create rows in `subscription_topics` to link it to existing subscriptions.
- **Query patterns**: to fetch all topics for a subscription, join `subscriptions` → `subscription_topics` → `supported_topics`. To find all subscribers of a topic, reverse the join direction.
- **Maintain referential integrity**: never insert into `subscription_topics` without first ensuring both the subscription and topic exist in their parent tables; the database will reject violations.
- **Region request workflow**: new region requests go into `region_requests` with status `pending`. Votes are recorded in `region_votes`. When `vote_count` meets `threshold`, approve the request and add the region to `regions`.
