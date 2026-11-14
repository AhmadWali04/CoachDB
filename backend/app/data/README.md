# Track B historical retrieval handoff

Codex owns this slice on `b/data-memory`. Claude continues pitch and voice on
`b/track-b-experience`; no frontend, API, schema, engine or voice files change here.

## Track A integration

```python
from app.data import search_experiences, search_styles

styles = await search_styles(
    db.style_profiles,
    query_vector,
    embedding_model="your-embedding-model-and-version",
    dimensions=384,
)
experiences = await search_experiences(
    coach_view.team_id,
    db.coach_experiences,
    query_vector,
    namespace=coach_view.memory_namespace,
    before=frozen_decision_timestamp,
    embedding_model="your-embedding-model-and-version",
    dimensions=384,
)
```

Use async collections (PyMongo AsyncCollection shape), with finite server-selection
and socket timeouts and timezone-aware BSON decoding (`tz_aware=True`). Dimensions
must match the actual embedding model and provisioned indexes; 384 is an example,
not a model selection. Supply the same frozen timezone-aware decision timestamp
when resuming a checkpoint. An empty list means no usable historical context;
continue coaching from the authoritative CoachView. Invalid input or a namespace
violation raises; service failures return an empty list and log a generic warning.
The adapter is read-only and does not create a connection, index, or embedding.

`StyleHit` includes `profile_id`, `summary`, `source`, `source_match_id`, `score`.
`ExperienceHit` includes `experience_id`, `namespace`, `summary`,
`verified_outcome`, `occurred_at`, `score`. Similarity scores are not confidence or
proof of tactical success. Historical results remain hints; cite their IDs and
verify facts against the source records.

## Storage and index contract

Each style document has the StyleHit fields (except computed `score`),
`namespace="public:styles"`, `embedding_model`, and `embedding` (finite vector).
Each experience document has the ExperienceHit fields (except `score`),
`verified=True`, `embedding_model`, and `embedding`. `occurred_at` is the time the
outcome was verified, stored as a BSON date. Writers must use the engine's
repository layer and guardrail and must not label recommendations as verified
outcomes. Store only concise summaries and source references, never raw datasets
or audio blobs. No writes are implemented in this slice.

Provision Atlas Vector Search indexes explicitly before integration:

- `style_profiles`: name `style_profiles_vector`, type `vectorSearch`, definition
  `vector_index_definition(dimensions)`.
- `coach_experiences`: name `coach_experiences_vector`, type `vectorSearch`,
  definition `vector_index_definition(dimensions, experiences=True)`.

Import the builder from `app.data.indexes`. Both definitions index `namespace`
and `embedding_model` as filter fields; experiences additionally index `verified`
and `occurred_at`. Query filters run inside `$vectorSearch`, with namespace
validation before any database access and a second check on experience results.
See [MongoDB's vector query documentation](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/).

## Dependencies still open

This PR does not load data or provision Atlas. The StatsBomb/Metrica ingestion
script, dataset-derived profiles, storage-size verification, real Atlas smoke test,
and frontend attribution are still checklist tasks. No fabricated dataset profiles
or simulator fixtures are included. Claude's frontend should display attribution
once those profiles are used: [StatsBomb Open Data](https://github.com/statsbomb/open-data)
and [Metrica Sports sample data](https://github.com/metrica-sports/sample-data).
Follow the providers' license and attribution instructions before distribution.

## Verification

From `backend/`, with the project's development dependencies installed:

```sh
python -m pytest tests app/data/tests -q
ruff check app/data
ruff format --check app/data
```

Tests are colocated to avoid overlapping Track A's test files. Include
`app/data/tests` explicitly; the current default pytest configuration scans `tests`.
They cover query isolation for both teams, foreign-result defense, verification
and time cutoffs, unavailable indexes/services, cursor errors and deadlines,
cancellation, validation, bounded results, attribution, and index filter coverage.
