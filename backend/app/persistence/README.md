# Track A persistence handoff

`MongoMatchRepository` stores typed simulator output and persisted decisions.
It accepts the shared synchronous Mongo database from `app.config.mongo.get_db()`;
use timezone-aware BSON decoding (`tz_aware=True`) as the shared client does.
Provision the repository's regular Mongo indexes with `ensure_indexes()` explicitly
before use. This does not build Atlas Vector Search indexes or grant permissions.

```python
from app.config.mongo import get_db
from app.persistence import MongoMatchRepository

repository = MongoMatchRepository(get_db())
repository.ensure_indexes()
repository.create_match(authoritative_initial_state)
repository.append_event(simulator_event)
repository.append_frame(simulator_frame)
repository.update_match(next_authoritative_state, expected_state_version=previous_version)
repository.save_decision(validated_decision)
latest = repository.get_latest_decision(match_id, team_id)
```

The simulator/orchestrator supplies match truth. Creating a match or appending an
identical event, frame or decision with the same stable key is idempotent. Reusing
that key for different content raises `PersistenceConflict`. Writes normalize BSON
millisecond timestamp precision so a retry does not conflict merely because
MongoDB rounded a timestamp. Naive timestamps are rejected.

Match updates require an increasing version and use an atomic compare-and-swap
on `match_id` and the previous `state_version`, without upsert. A missing match or
stale version raises `PersistenceConflict`; reload and reconcile before retrying.
This is optimistic concurrency, not worker lease/fencing enforcement. Actions,
leases, checkpoints, recovery and verified-action lifecycle remain separate work.

Events/frames/decisions require a persisted match. Decisions must have consistent
match/team/coach identity, rival identity and report snapshot versions. The latest
decision query is scoped by match/team and sorts by timestamp and ID. It satisfies
`voice.decisions.CoachDecisionReader`: pass `decisions=repository` when constructing
`BriefingService`. This PR does not modify Track B's voice dependency wiring.

`get_frames(match_id, from_seq=0, limit=50)` returns typed frames ordered by sequence.
`get_events(match_id, after_event_id=None, limit=200)` returns typed events ordered
by half, step, then stable event ID. A cursor must belong to that match. Limits are
bounded to 1–200. The API layer can construct its existing `FramesPage` without
changing the frame contract. No HTTP endpoints are changed in this slice.

Indexes cover matches, events, frames, decisions, actions and tasks. Action/task
indexes prepare those collections; their repositories/state machines are still
pending, so the parent persistence checklist remains in progress. Multi-document
writes are not one transaction: a workflow must checkpoint meaningful boundaries
and reconcile partial writes. Database failures propagate; there is no process
memory fallback and no claim that a submitted action has been verified.

Verification from `backend/`:

```sh
python -m pytest tests app/data/tests -q
ruff check app/persistence tests/test_persistence.py tests/test_persistence_integration.py
ruff format --check app/persistence tests/test_persistence.py tests/test_persistence_integration.py
```

An optional real-driver round trip is in `tests/test_persistence_integration.py`.
It uses `TEST_MONGODB_URI` only, writes a uniquely named test database, verifies a
fresh client can read the records, and deletes only that test database afterward.
Without that environment variable it is skipped; unit tests use mocked collections.
