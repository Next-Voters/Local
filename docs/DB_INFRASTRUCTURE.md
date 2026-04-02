# Database Infrastructure

This refactor enforces consistency for supported cities and topics by centralizing lookup tables and using formal foreign-key constraints to link them to subscriptions. A junction table implements the many-to-many relationship between subscriptions and topics, ensuring the SQL engine formally recognizes all relational dependencies.

## subscriptions

| Column | Type | Notes |
| --- | --- | --- |
| `contact` | `text` | Primary key; subscriber email or handle. |
| `city` | `text` | Foreign key → `supported_cities.city`. |
| `preferred_language` | `text` | Nullable foreign key → `supported_languages.language`. Defaults to `NULL` (treated as English). |

Each subscription holds a unique contact identifier, references exactly one city, and optionally specifies a preferred report language. Topics are managed through the `subscription_topics` junction table.

## supported_cities

| Column | Type | Notes |
| --- | --- | --- |
| `city` | `text` | Primary key; canonical city label referenced by `subscriptions.city`. |

This lookup table constrains subscriptions to the vetted list of launch markets while keeping the city strings human-readable.

## supported_languages

| Column | Type | Notes |
| --- | --- | --- |
| `language` | `text` | Primary key; canonical language name referenced by `subscriptions.preferred_language`. |
| `description` | `text` | Human-readable label (e.g., "Español", "Français"). |

This lookup table constrains the `preferred_language` column on subscriptions. Seeded with English, Spanish, and French. New languages must be inserted here before they can be assigned to subscribers.

## supported_topics

| Column | Type | Notes |
| --- | --- | --- |
| `topic_id` | `integer` | Identity primary key; referenced by `subscription_topics.topic_id`. |
| `topic_name` | `text` | Unique canonical label (e.g., `immigration`, `civil rights`, `economy`). |
| `description` | `text` | Short explanation of what the topic covers. |

The initial seed rows capture the three core topics (immigration, civil rights, economy). New topics must be inserted here first so the junction table can reference their IDs.

## subscription_topics (Junction Table)

| Column | Type | Notes |
| --- | --- | --- |
| `subscription_id` | `text` | Foreign key → `subscriptions.contact` (ON DELETE CASCADE). |
| `topic_id` | `integer` | Foreign key → `supported_topics.topic_id` (ON DELETE CASCADE). |

This junction table implements the **many-to-many relationship** between subscriptions and topics. Each row links one subscription to one topic; a subscription can have multiple topic rows, and a topic can be referenced by multiple subscriptions. Both foreign keys enforce referential integrity and cascade deletes to keep the junction table clean.

## Entity Relationships

```mermaid
erDiagram
    supported_cities ||--o{ subscriptions : "city"
    supported_languages ||--o{ subscriptions : "preferred_language"
    supported_topics ||--o{ subscription_topics : "topic_id"
    subscriptions ||--o{ subscription_topics : "contact"
```

The diagram shows:
- `supported_cities` supplies city references that `subscriptions` must conform to (one-to-many).
- `supported_languages` supplies language references that `subscriptions.preferred_language` must conform to (one-to-many, nullable).
- `subscriptions` and `supported_topics` are linked through the `subscription_topics` junction table, forming a many-to-many relationship. This allows any subscription to span multiple topics, and any topic to be selected by multiple subscribers.
- Formal foreign-key constraints are enforced on all edges, preventing orphaned references and maintaining data integrity across the entire schema.

## Operational Guidance

- **Seed lookup tables first**: ensure all topics and cities exist in their respective lookup tables before creating subscriptions or junction table entries.
- **Insert topics before linking**: when adding a new topic, insert it into `supported_topics`, then create rows in `subscription_topics` to link it to existing subscriptions.
- **Leverage cascade deletes**: if a subscription or topic is deleted, the corresponding junction table rows are automatically removed, keeping the schema clean.
- **Query patterns**: to fetch all topics for a subscription, join `subscriptions` → `subscription_topics` → `supported_topics`. To find all subscribers of a topic, reverse the join direction.
- **Maintain referential integrity**: never insert into `subscription_topics` without first ensuring both the subscription and topic exist in their parent tables; the database will reject violations.

## Code Integration

All tables are queried via `utils/supabase_client.py`:

- `get_supported_topics()` → `list[str]` of topic names from `supported_topics`
- `get_supported_languages()` → `list[str]` of language names from `supported_languages`
- `get_all_subscribers_with_cities_and_topics()` → `list[dict]` with `contact`, `city`, `topics`, and `preferred_language` keys (uses PostgREST nested join through `subscription_topics`)
- `get_subscribers_for_topic(topic)` → `list[str]` of emails via `subscription_topics` inner join

The email dispatcher (`pipelines/node/email_dispatcher.py`) uses subscriber topic and language preferences to build per-subscriber filtered emails in their preferred language.
