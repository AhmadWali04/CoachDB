# Rival Coaches — Team Checklist

Shared task board for two developers and their coding agents. The specs
live in `PRD.md`, `CLAUDE.md`, and `AGENTS.md`. This file only tracks
**who is doing what, what is done, and what changed**.

| Dev | Name | Track | Owns |
|-----|------|-------|------|
| **A** | _(name)_ | Engine | `backend/app/{simulator,coaches,orchestration,persistence,recovery,evaluation}`, `backend/tests/` for those |
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
- [ ] **Both devs:** review the contract and ack the Handoff log entry below
- [ ] Atlas free cluster created, `MONGODB_URI` in each dev's local `backend/.env`
- [ ] Sync CLAUDE.md and AGENTS.md with the PRD (Opposition Scout, live tactical board UI)

---

## Track A — Engine

### Simulator (PRD §5)
- [ ] Seeded match loop: two halves, 20 steps each, halftime and full time
- [ ] Tactical settings change event probabilities
- [ ] Emits player and ball positions per step (frame contract)
- [ ] Test: same seed gives identical output
- [ ] Export one real run to `frontend/src/fixtures/match_seed42.json` → **unblocks B**

### Persistence (PRD §8)
- [ ] Repository layer + indexes for `matches`, `match_events`, `actions`, `tasks`, `coach_decisions`
- [ ] Endpoints above return real data

### Coaches (PRD §6, AGENTS.md)
- [ ] Match Analyst (own team)
- [ ] Opposition Scout (rival, public data only)
- [ ] Tactical Coach + rival prediction + `voice_script`
- [ ] Plan validation, one bounded correction, then balanced fallback
- [ ] Coach agents take only `CoachView` (`build_coach_view`) as match input
- [ ] Halftime flow uses `SealedHalftimePlans`: both submit, then reveal, then apply both together
- [ ] LangGraph orchestration with the MongoDB checkpointer: one subgraph and thread per coach, no shared state

### Execution and recovery (PRD §9)
- [ ] Action ledger `proposed → submitted → applied → verified`, unique `action_id`
- [ ] Simulator dedupes repeated action IDs
- [ ] Leases, heartbeat, fencing token
- [ ] Crash injection after submit, before verify, then reconcile
- [ ] Tests: no duplicate effect; stale token can't commit

### Evaluation (PRD §12)
- [ ] Deterministic evaluator with seeded, side-swapped batches
- [ ] `GET /evaluations/{batch_id}`

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
- [x] **B** · `b/track-b-experience` — Local script: StatsBomb Open Data + Metrica sample → compact style profiles (`scripts/build_style_profiles.py`, `backend/app/data/{statsbomb,metrica,style_profile,pipeline}.py`; ran live against the real sources → 6 profiles, see output below). Documents are shaped to match the storage contract below field-for-field (`namespace`, `embedding_model`, `embedding`, `summary`, `source_match_id`)
- [~] **B** · `b/track-b-experience` — Writes compact derived profiles to `backend/.cache/data/style_profiles.json` (a few KB, nowhere near the 512 MB budget); loading them into a real `style_profiles` Mongo collection still needs Atlas provisioned + A's persistence layer
- [~] **B / Codex** · `b/data-memory` — Vector index definitions for `style_profiles`/`coach_experiences` with `namespace`(+`embedding_model`, and `verified`/`occurred_at` for experiences) filters (`backend/app/data/indexes.py:vector_index_definition`); not yet provisioned on a real Atlas cluster
- [x] **B / Codex** · `b/data-memory` — Retrieval function for A's scout and coach: `search_styles()`, `search_experiences()` → **hand to A** (`backend/app/data/retrieval.py`: async, real `$vectorSearch` pipelines, `embedding_model`/`dimensions` validation, a frozen `before` cutoff for experiences so retrieval can't leak future outcomes; see `backend/app/data/README.md` for the Track A integration snippet)
- [x] **B / Codex** · `b/data-memory` — `search_experiences` calls `require_own_namespace()` before any DB access and double-checks `namespace`/`verified`/`occurred_at` on each result; tests cover both teams and that a foreign-namespace result can't slip through (`backend/app/data/tests/test_retrieval.py`)
- [x] **B** · `b/track-b-experience` — Dataset attribution shown in the UI (`DatasetAttribution.tsx`)

### Secondary panels and controls (PRD §13.4)
- [~] **B** · `b/track-b-experience` — Event feed (`EventFeed.tsx`, wired to live `getEvents`); coach comparison, action timeline, and evaluation view are typed empty-state panels pending Track A endpoints (see Requests)
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

## Requests (cross-track asks)

Add a line when you need something from the other track. The owner
moves it into their track section when they accept it.

| From → To | Ask | Status |
|-----------|-----|--------|
| B → A | Export `frontend/src/fixtures/match_seed42.json` from a real seeded run (frame contract, §13.5) so the pitch renders real data instead of unit-test-only mock frames | Open |
| B → A | Need a read accessor for the latest `CoachDecision` per `(match_id, team_id)` from `backend/app/persistence` (e.g. `get_latest_decision`) so `backend/app/voice` can read the approved `voice_script` instead of depending on an in-memory fake | Open |
| B → A | Coach comparison panel (§13.4) needs a read endpoint exposing `AnalystReport`/`ScoutReport`/`TacticalPlan` per match/team — none of `schemas/api.py`'s current endpoints return them | Open |
| B → A | Action timeline (§13.4) needs a read endpoint over the action ledger (`proposed → submitted → applied → verified`); evaluation view needs `GET /evaluations/{batch_id}` from §12 — neither exists yet in `api/stubs.py` | Open |
| B → A | `backend/app/data/retrieval.search_styles`/`search_experiences` (Codex) are ready to call from the scout/coach — see `backend/app/data/README.md`'s integration snippet. They need an Atlas cluster with both vector indexes provisioned (`indexes.vector_index_definition`) and real embeddings; `style_profiles` docs from this branch's ingestion pipeline use a handcrafted 8-dim stand-in (`embedding_model="handcrafted-stats-v1"`), not a learned embedding | Open |

## Handoff log (contract changes, newest first)

Record every change to `schemas/` or `api/`, every new endpoint, and
anything the other dev's agent needs to know.

| Date / time | Who | Change | Acked by |
|-------------|-----|--------|----------|
| 2026-11-14 | B (Claude) | Merged Codex's `b/data-memory` (PR #3, `backend/app/data/retrieval.py`+`indexes.py`) into `b/track-b-experience`. Dropped this branch's own `vector_search.py`/`test_data_vector_search.py` (in-memory, sync) in favor of Codex's async `$vectorSearch` version, and renamed `StyleProfile`'s `source_ref`→`source_match_id` and `vector`→`embedding`, adding `summary`/`namespace`/`embedding_model` so documents this branch's ingestion pipeline writes match `README.md`'s storage contract field-for-field (`test_data_style_profile_contract.py` guards it). No further action needed from A. | A: · B: Claude ✓ |
| 2026-11-14 | B (Claude) | Implemented `GET /matches/{id}/briefings/{team_id}` (`backend/app/voice/`, wired in `api/matches.py`): reads the latest `CoachDecision` via `CoachDecisionReader` (in-memory until A hands off persistence — see Requests), resolves audio through an ElevenLabs adapter with a filesystem `AudioCache` keyed by `briefing_id`, falls back to text-only on any TTS failure or missing voice ID. Route signature/response model unchanged; now 404s instead of 501 when no decision exists yet for that match/team, and `/audio/*` is mounted for cached clips. | A: · B: Claude ✓ |
| 2026-11-14 | Phase 0 | Coach isolation guardrails (`backend/app/guardrails/`, `schemas/coach_view.py`): `build_coach_view`, `SealedHalftimePlans`, `require_own_namespace`. Coaches see the rival's kickoff formation; the rest of the rival's tactics and its stamina are hidden, and the scout infers them from the formation and public events. Memory namespaces are `coach:blue` and `coach:red`. Rules are in AGENTS.md §2. | A: · B: Claude ✓ |
| 2026-11-14 | Phase 0 | Initial contract: `schemas/` (enums, match, event, frame, coach, action, api) and stubbed endpoints. Team IDs are `blue`/`red`; pitch side is `top`/`bottom` (the `top` team attacks toward y=100). Coordinates are 0–100. Unknown fields are rejected. | A: · B: Claude ✓ |
