# Track B historical retrieval handoff

Codex owns this slice on `b/data-memory`. Claude continues pitch and voice on
`b/track-b-experience`; no frontend, API, schema, engine or voice files change here.

## Style profiles (StatsBomb + Metrica)

Build and load (raw files cached in `backend/.cache/data/raw/`, gitignored):

```bash
docker compose up -d   # or use the Atlas cluster's URI
MONGODB_URI='mongodb://localhost:27017/?directConnection=true' \
  backend/.venv/bin/python scripts/build_style_profiles.py --load
```

Default set: the first 16 FIFA World Cup 2022 matches plus Metrica sample
games 1 and 2, which gives 36 profiles (about 56 KB). `--max-matches` widens it.

Metrica profiles also use the tracking files (about 125 MB raw, cached;
`--no-tracking` skips them), via `metrica_tracking.py`:
- formation inferred from the starting outfield players' average positions
  out of possession in the first half (`formation_source="tracking"`), so it is
  the defensive shape, which may differ from the attacking lineup;
- `defensive_line_height_m`, `block_length_m`, `block_width_m` while the
  opponent has the ball, with possession taken from the synchronized events.
  For Metrica, the defensive line label uses the tracked line height.

StatsBomb formations come from the announced lineup (`formation_source="lineup"`).

Each profile carries tactics labels in the scout's vocabulary (pressing,
defensive line, tempo, mentality, attack focus, formation) and a 9-dimension
`tactical-style-v1` embedding (`tactical_style.py`). Labels are percentiles
**within each dataset**, so "high press" means high relative to the other
teams in that dataset. Always rebuild and reload the whole set.

## Track A integration

The scout queries styles with its inferred rival tactics:

```python
from app.data import search_experiences, search_styles
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector

vector = style_query_vector(scout_report.observed_tactics)  # None if nothing inferred
styles = (
    []
    if vector is None
    else await search_styles(
        db.style_profiles,
        vector,
        embedding_model=EMBEDDING_MODEL,
        dimensions=DIMENSIONS,
        limit=3,
    )
)
# Cite hits as `profile:<profile_id>` in ScoutReport.closest_style_profile_ids.
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

## Provision the private experience index

Codex owns this follow-up on `b/experience-index`; Claude's secondary frontend
panels remain on their separate branch. Track A must choose the experience
embedding model and its dimensions before provisioning the shared index. Do not
reuse the style-profile dimensions unless the experience writer uses that model.

Preview without a connection or credentials (8 is only an example):

```sh
backend/.venv/bin/python scripts/provision_experience_index.py --dimensions 8
```

Once Track A confirms the dimensions, add `--apply`. The command reads
`MONGODB_URI` and `MONGODB_DATABASE` from the environment or `backend/.env`.
It creates the empty `coach_experiences` collection when absent, then creates
`coach_experiences_vector` with namespace/model/verified/time filters. It does
not read or insert experiences and does not grant access or change users.

Provisioning is idempotent: matching indexes are reused, incompatible definitions
are rejected without rebuilding or dropping them. The command reports success
only after the index is both `READY` and queryable. `--wait-seconds` defaults to
30 (maximum 300); a timeout may leave a build in progress. Rerun the same command
rather than dropping the index. Driver errors omit credential-bearing details.
See [MongoDB's index documentation](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/).

The CLI/helper tests use fakes; shared Atlas provisioning and an actual retrieval
smoke test remain pending the experience writer's model choice. Run the tests
with `python -m pytest tests app/data/tests -q` from `backend/`.
