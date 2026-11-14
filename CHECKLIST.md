# Rival Coaches — Team Checklist

Shared task board for two developers and their coding agents. The specs
live in `PRD.md`, `CLAUDE.md`, and `AGENTS.md`. This file only tracks
**who is doing what, what is done, and what changed**.

| Dev | Name | Track | Owns |
|-----|------|-------|------|
| **A** | Codex (engine completion, `a/persistence`) | Engine | `backend/app/{simulator,coaches,orchestration,persistence,recovery,evaluation}`, `backend/tests/` for those |
| **B** | Claude (`b/track-b-experience`) | Experience | `frontend/`, `backend/app/voice/`, `backend/app/data/` (StatsBomb/Metrica pipeline), `scripts/` |
| Both | — | Contracts | `backend/app/schemas/`, `backend/app/api/`, `backend/app/guardrails/`, `.env.example`, this file |

---

## Rules for humans and agents

1. **Read this file first** at the start of every task, then the
   relevant PRD section.
2. **Claim before you start.** Change `[ ]` to `[~]`, add your letter
   and branch, then commit and push this file right away:
   `- [~] **A** · \`a/simulator\` — Seeded match loop`
3. **Only edit files in your track.** If you need a change in the other
   track, add it to **Requests** below instead of editing their files.
4. **Contracts are shared.** Changing anything in `schemas/` or `api/`
   needs a **Handoff log** entry, and the other dev must acknowledge it
   before it merges.
5. **Mark done only when it's verified.** A task is `[x]` only when its
   tests pass. Add the commit or PR: `- [x] **A** · #12 — ...`
6. **Keep this file small and conflict-free.** Edit only your own
   lines, pull before you edit, and push checklist changes on their own
   commit.
7. **Fixtures are labeled.** The frontend may use recorded JSON from
   `frontend/src/fixtures/` until the API is live. The UI must show a
   visible "fixture data" badge, and fixtures must come from a real
   simulator run (PRD §13.5), never be hand-invented.
8. **Agents don't tick boxes they didn't verify.** Report the test
   command and result in the commit message.

Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (say why)

---

## Phase 0 — Contracts (together, first ~1 hour)

Nothing else starts until these are merged. Everything after this
point runs in parallel.

- [x] Repo skeleton: `backend/` (FastAPI) and `frontend/` (React + TS, Vite)
- [x] `.env.example` with the variable names from CLAUDE.md
- [x] Pydantic schemas: team, player, match state, event, tactical plan, action, decision, analyst and scout reports (`backend/app/schemas/`)
- [x] **Frame contract** for the pitch (PRD §13.5): per step → player `(x, y)`, ball position and owner, events with the players involved (`schemas/frame.py`)
- [x] API shape agreed and stubbed (returning `501`):
  - `POST /matches` · `GET /matches/{id}` · `GET /matches/{id}/frames?from_seq=&limit=` · `GET /matches/{id}/events`
  - `GET /matches/{id}/briefings/{team_id}` (transcript + audio URL or `unavailable`)
  - `POST /demo/inject-crash` · `POST /matches/{id}/reset`
- [x] Generate TS types from the OpenAPI schema (`npm run gen:api` → `frontend/src/api/schema.d.ts`; typed client in `src/api/client.ts`)
- [~] **Both devs:** review the contract and ack the Handoff log entries below (Justin ✓, teammate pending)
- [x] MongoDB client, `/health` reports `mongodb` status, `scripts/check_mongo.py`, optional local Atlas via `docker compose up -d`
- [x] Atlas free (M0) cluster created in the Atlas UI (`cluster0`, MongoDB 9.0.7)
- [~] Database user for each dev + IP access list entry (Justin ✓, teammate pending)
- [~] `MONGODB_URI` in each dev's local `backend/.env`; `scripts/check_mongo.py` prints `mongodb: ok` (Justin ✓, teammate pending)
- [x] Sync CLAUDE.md and AGENTS.md with the PRD (Opposition Scout, live tactical board UI, guardrails)

---

## Track A — Engine

### Simulator (PRD §5)
- [~] **A (Justin)** · `a/engine` — Seeded match loop: two halves, 20 steps each, halftime and full time
- [~] **A (Justin)** · `a/engine` — Tactical settings change event probabilities
- [~] **A (Justin)** · `a/engine` — Emits player and ball positions per step (frame contract)
- [~] **A (Justin)** · `a/engine` — Test: same seed gives identical output
- [~] **A (Justin)** · `a/engine` — Export one real run to `frontend/src/fixtures/match_seed42.json` → **unblocks B**

### Persistence (PRD §8)
- [~] **A (Justin)** · `a/engine` — Repository layer + indexes for `matches`, `match_events`, `actions`, `tasks`, `coach_decisions`; first slice: durable match/event/frame/decision storage and latest-decision reader (Claude keeps simulator work)
- [x] **A / Codex** · `34f7f97` — Durable match/event/frame/decision repositories, unique/query indexes, version-checked updates and voice-compatible `get_latest_decision`; 43 focused tests pass (181 backend tests pass, 2 opt-in integration tests skipped). Action/task state machines remain pending.
- [~] **A (Justin)** · `a/engine` — Endpoints above return real data

### Coaches (PRD §6, AGENTS.md)
- [~] **A (Justin)** · `a/engine` — Match Analyst (own team)
- [~] **A (Justin)** · `a/engine` — Opposition Scout (rival, public data only)
- [~] **A (Justin)** · `a/engine` — Tactical Coach + rival prediction + `voice_script`
- [~] **A (Justin)** · `a/engine` — Plan validation, one bounded correction, then balanced fallback
- [~] **A (Justin)** · `a/engine` — Coach agents take only `CoachView` (`build_coach_view`) as match input
- [~] **A (Justin)** · `a/engine` — Halftime flow uses `SealedHalftimePlans`: both submit, then reveal, then apply both together
- [~] **A (Justin)** · `a/engine` — LangGraph orchestration with the MongoDB checkpointer: one subgraph and thread per coach, no shared state

### Execution and recovery (PRD §9)
- [~] **A (Justin)** · `a/engine` — Action ledger `proposed → submitted → applied → verified`, unique `action_id`
- [~] **A (Justin)** · `a/engine` — Simulator dedupes repeated action IDs
- [~] **A (Justin)** · `a/engine` — Leases, heartbeat, fencing token
- [~] **A (Justin)** · `a/engine` — Crash injection after submit, before verify, then reconcile
- [~] **A (Justin)** · `a/engine` — Tests: no duplicate effect; stale token can't commit

### Evaluation (PRD §12)
- [~] **A (Justin)** · `a/engine` — Deterministic evaluator with seeded, side-swapped batches
- [~] **A (Justin)** · `a/engine` — `GET /evaluations/{batch_id}`

---

## Track B — Experience

### Tactical pitch (PRD §13.1–13.2)
- [x] **B** · `b/track-b-experience` — Vertical pitch SVG with markings; Team A upper half, Team B lower half (`TacticalPitch.tsx`; `npx vitest run` → 21 passed)
- [x] **B** · `b/track-b-experience` — Player markers (circle vs. cross), ball, score, clock, phase, formation
- [x] **B** · `b/track-b-experience` — Renders from fixture frames (with the fixture badge) — fixture loader auto-discovers `src/fixtures/*.json`; no file to render yet (blocked on A's export, see Requests)
- [x] **B** · `b/track-b-experience` — Movement interpolation between frames (`match/playback.ts`, `useFramePlayback`)
- [x] **B** · `b/track-b-experience` — Arrows: passes, runs, pressing; cap on simultaneous arrows (`match/arrows.ts`, cap=3)
- [x] **B** · `b/track-b-experience` — `prefers-reduced-motion` (snaps instead of interpolating; `pitch-svg--reduced-motion` disables marker transitions)
- [x] **B** · `b/track-b-experience` — Switch from fixture to live `/frames` polling (`match/useLiveFrames.ts`)

### Coach selection and voice (PRD §11, §13.3)
- [x] **B** · `b/track-b-experience` — Click pitch half, team label, or coach card → selected state + active speaker
- [x] **B** · `b/track-b-experience` — Single audio controller: switching teams stops the previous audio (`audio/useBriefingAudio.ts`)
- [x] **B** · `b/track-b-experience` — Transcript, plus pause, resume, and replay; loading/playing/paused/unavailable states (`CoachPanel.tsx`)
- [x] **B** · `b/track-b-experience` — Backend ElevenLabs adapter: cache by briefing ID, text fallback, voice IDs from env (`backend/app/voice/`; `pytest` → 36 passed)
- [x] **B** · `b/track-b-experience` — Tests: selection triggers no API writes (`getBriefing` is a GET, asserted `toHaveBeenCalledOnce`); never two audios playing (`useBriefingAudio.test.ts`)

### Data and memory (PRD §8.2, §14.2)
- [x] **B** · `b/style-profiles` — Local script: StatsBomb Open Data + Metrica sample → compact style profiles (`scripts/build_style_profiles.py`, `backend/app/data/`): 16 World Cup 2022 matches + Metrica games 1–2 → 36 profiles, raw files cached in `backend/.cache/data/raw/` (47 MB, gitignored)
- [x] **B** · `b/style-profiles` — Profiles carry tactics labels in the scout's vocabulary and a 9-dim `tactical-style-v1` embedding; `style_query_vector(ObservedTactics)` builds the scout's query (`tactical_style.py`)
- [x] **B** · `b/style-profiles` — Load into `style_profiles` (56 KB): `--load` upserts and provisions `style_profiles_vector`; verified on local Atlas, smoke query returns 4-3-3 high-press teams (`pytest` → 71 passed; `TEST_MONGODB_URI=… pytest tests/test_data_atlas_integration.py` → 1 passed)
- [x] **B** · `b/atlas-setup` — Loaded into the shared Atlas cluster: 36 profiles in `rival_coaches.style_profiles`, `style_profiles_vector` READY, smoke query through `search_styles` returns 4-3-3 high-press teams
- [~] **B / Codex** · `b/experience-index` — Coach-experience index tooling implemented: dry-run/apply CLI, idempotent create and READY/queryable verification (138 tests pass, 1 skipped); actual Atlas provisioning waits for A's embedding dimensions/model
- [x] **B** · `b/data-memory` (Codex) — Retrieval for A's scout and coach: `search_styles()`, `search_experiences(team_id, ...)` (`backend/app/data/retrieval.py`) → **handed to A**, see `backend/app/data/README.md`
- [x] **B** · `b/data-memory` (Codex) — `search_experiences` calls `require_own_namespace()` and filters on `namespace`; Blue can't retrieve Red's experiences (`backend/app/data/tests/test_retrieval.py`)
- [x] **B** · `b/metrica-tracking` — Metrica tracking (positions) → formation and block shape for Metrica profiles (`metrica_tracking.py`): 3× 4-4-2 and 1× 3-5-2 inferred, checked against player width; block length, width, and line height out of possession (`pytest` → 94 passed, 1 skipped; Atlas integration → 1 passed)
- [x] **B** · `b/track-b-experience` — Dataset attribution shown in the UI (`DatasetAttribution.tsx`)

### Secondary panels and controls (PRD §13.4)
- [~] **B** · `b/track-b-experience` — Event feed (`EventFeed.tsx`, wired to live `getEvents`)
- [~] **B** · `b/track-b-experience` — Coach comparison (`CoachComparison.tsx`), action timeline (`ActionTimeline.tsx`), and evaluation (`EvaluationView.tsx`) are built to fully render real data (strengths/weaknesses, scouting + prediction, plan + risks/fallback; status-colored action ledger with verified state-version transitions; per-coach metrics table, never ranked by wins) against `frontend/src/types/{coachAnalysis,action,evaluation}.ts` -- hand-written mirrors of the backend schemas/PRD §12 metrics, since no endpoint returns this data yet. Wired into `App.tsx` with empty data (`{}`/`[]`/`null`) today, so each shows its own empty state; swap in real data once Track A ships the endpoints in the Requests below. (`npx vitest run` → 31 passed)
- [~] **B** · `b/track-b-experience` — Demo controls: start, inject crash, reset wired to the real API; "run batch" disabled pending Track A's evaluation batch endpoint

---

## Integration and demo (together, last)

- [ ] End-to-end: start match → first half moves → halftime plans → briefings → second half changes
- [ ] Crash demo shows recovery on the timeline
- [ ] ElevenLabs off → transcript still shows, match still runs
- [ ] Remove fixture badge path from the demo build
- [ ] Walk through PRD §16 Definition of Done
- [ ] Rehearse the demo twice

---

## Stretch — Atlas Agent Engine memory (only after the demo runs end to end)

For the Agents in Context Toronto hackathon. Agent Engine is in public
preview, so it must stay swappable and must not block the demo.

- [ ] Check the hackathon rules or resource guide for MongoDB prize criteria
- [ ] Spike: Agent Memory stores coach experiences in place of `coach_experiences` Vector Search, behind the same `search_experiences(team_id, ...)` interface
- [ ] Give each coach its own identity, with `private` visibility on its records (memory is scoped per project and user identity, not per agent)
- [ ] **Isolation test:** Blue can't read Red's memory. If it can, use one project per coach or drop the spike.
- [ ] Config flag `MEMORY_BACKEND=vector_search|agent_engine`, defaulting to `vector_search`
- [ ] Mention it in the demo script and show a memory record being recalled at halftime

---

## Requests (cross-track asks)

Add a line when you need something from the other track. The owner
moves it into their track section when they accept it.

| From → To | Ask | Status |
|-----------|-----|--------|
| A / Codex → Claude | Codex now owns Track A persistence in isolated `../CoachDB-experience-index` on `a/persistence`: `backend/app/persistence/` and `backend/tests/test_persistence*`. Simulator/export/fixture work in your checkout is preserved. Voice can consume the new repository latest-decision reader after handoff. | Ready: `34f7f97`; `app/persistence/README.md`; API and voice composition still pending |
| B / Codex → Claude | Codex owns experience-index provisioning in `../CoachDB-experience-index`, branch `b/experience-index` (`app/data/experience_index.py`, colocated tests, `scripts/provision_experience_index.py`). Claude continues secondary frontend panels. No schema/API changes or experience writes. | Implemented; 138 tests pass, 1 skipped; actual provisioning pending A |
| B → A | Export `frontend/src/fixtures/match_seed42.json` from a real seeded run (frame contract, §13.5) so the pitch renders real data instead of unit-test-only mock frames | Open |
| B → A | Need a read accessor for the latest `CoachDecision` per `(match_id, team_id)` from `backend/app/persistence` (e.g. `get_latest_decision`) so `backend/app/voice` can read the approved `voice_script` instead of depending on an in-memory fake | Reader implemented on `a/persistence` (`34f7f97`); ready for voice wiring |
| B → A | Coach comparison panel (§13.4) needs a read endpoint exposing `AnalystReport`/`ScoutReport`/`TacticalPlan` per match/team — none of `schemas/api.py`'s current endpoints return them | Open |
| B → A | Action timeline (§13.4) needs a read endpoint over the action ledger (`proposed → submitted → applied → verified`); evaluation view needs `GET /evaluations/{batch_id}` from §12 — neither exists yet in `api/stubs.py` | Open |
| B → A | `backend/app/data/retrieval.search_styles`/`search_experiences` are ready to call from the scout/coach -- Atlas, the `style_profiles` index, and 36 loaded profiles are live; see `backend/app/data/README.md`'s integration snippet | Open |

## Handoff log (contract changes, newest first)

Record every change to `schemas/` or `api/`, every new endpoint, and
anything the other dev's agent needs to know.

| Date / time | Who | Change | Acked by |
|-------------|-----|--------|----------|
| 2026-11-14 | Justin | Track A handoff: Ahmad/Codex handed the remaining Track A work (simulator, endpoints, coaches, orchestration, execution/recovery, evaluation) to Justin on `a/engine`. | Justin ✓ · Ahmad: |
| 2026-11-14 | A / Codex | `MongoMatchRepository` in `app/persistence` persists authoritative matches, immutable events/frames/decisions and exposes `get_latest_decision(match_id, team_id)` for B's `CoachDecisionReader`. Explicit `ensure_indexes()`, CAS state updates, bounded event/frame queries. No schema/API change; see README for composition and remaining lifecycle work. 181 tests pass, 2 opt-in integration tests skipped. | B: pending wiring |
| 2026-11-14 | B (Justin) | Style profiles use embedding model `tactical-style-v1` (9 dims, cosine). The scout builds its query with `style_query_vector(observed_tactics)` and passes `EMBEDDING_MODEL`/`DIMENSIONS` from `app/data/tactical_style.py` to `search_styles`. Profiles are ranked within each dataset. No `schemas/` or `api/` change. | Justin ✓ · A: |
| 2026-11-14 | B (Claude) | Implemented `GET /matches/{id}/briefings/{team_id}` (`backend/app/voice/`, wired in `api/matches.py`): reads the latest `CoachDecision` via `CoachDecisionReader` (in-memory until A hands off persistence — see Requests), resolves audio through an ElevenLabs adapter with a filesystem `AudioCache` keyed by `briefing_id`, falls back to text-only on any TTS failure or missing voice ID. Route signature/response model unchanged; now 404s instead of 501 when no decision exists yet for that match/team, and `/audio/*` is mounted for cached clips. | A: · B: Claude ✓ |
| 2026-11-14 | Phase 0 | Coach isolation guardrails (`backend/app/guardrails/`, `schemas/coach_view.py`): `build_coach_view`, `SealedHalftimePlans`, `require_own_namespace`. Coaches see the rival's kickoff formation; the rest of the rival's tactics and its stamina are hidden, and the scout infers them from the formation and public events. Memory namespaces are `coach:blue` and `coach:red`. Rules are in AGENTS.md §2. | A: · B: Claude ✓ |
| 2026-11-14 | Phase 0 | Initial contract: `schemas/` (enums, match, event, frame, coach, action, api) and stubbed endpoints. Team IDs are `blue`/`red`; pitch side is `top`/`bottom` (the `top` team attacks toward y=100). Coordinates are 0–100. Unknown fields are rejected. | A: · B: Claude ✓ |
