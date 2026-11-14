# Rival Coaches — Team Checklist

Shared task board for two developers and their coding agents. The specs
live in `PRD.md`, `CLAUDE.md`, and `AGENTS.md`. This file only tracks
**who is doing what, what is done, and what changed**.

| Dev | Name | Track | Owns |
|-----|------|-------|------|
| **A** | _(name)_ | Engine | `backend/app/{simulator,coaches,orchestration,persistence,recovery,evaluation}`, `backend/tests/` for those |
| **B** | _(name)_ | Experience | `frontend/`, `backend/app/voice/`, `backend/app/data/` (StatsBomb/Metrica pipeline), `scripts/` |
| Both | — | Contracts | `backend/app/schemas/`, `backend/app/api/`, `.env.example`, this file |

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

- [ ] Repo skeleton: `backend/` (FastAPI) and `frontend/` (React + TS, Vite)
- [ ] `.env.example` with the variable names from CLAUDE.md
- [ ] Pydantic schemas: team, player, match state, event, tactical plan, action, decision
- [ ] **Frame contract** for the pitch (PRD §13.5): per step → player `(x, y)`, ball position and owner, events with the players involved
- [ ] API shape agreed and stubbed (returning `501`):
  - `POST /matches` · `GET /matches/{id}` · `GET /matches/{id}/frames?from=` · `GET /matches/{id}/events`
  - `GET /matches/{id}/briefings/{team_id}` (transcript + audio URL or `unavailable`)
  - `POST /demo/inject-crash` · `POST /matches/{id}/reset`
- [ ] Generate TS types from the OpenAPI schema (shared source of truth for enums)
- [ ] Atlas free cluster created, `MONGODB_URI` in each dev's local `.env`

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
- [ ] Separate namespaces for the Blue and Red coaches; test that neither can read the other's
- [ ] LangGraph orchestration with the MongoDB checkpointer

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
- [ ] Vertical pitch SVG with markings; Team A upper half, Team B lower half
- [ ] Player markers (circle vs. cross), ball, score, clock, phase, formation
- [ ] Renders from fixture frames (with the fixture badge)
- [ ] Movement interpolation between frames
- [ ] Arrows: passes, runs, pressing; cap on simultaneous arrows
- [ ] `prefers-reduced-motion`
- [ ] Switch from fixture to live `/frames` polling

### Coach selection and voice (PRD §11, §13.3)
- [ ] Click pitch half, team label, or coach card → selected state + active speaker
- [ ] Single audio controller: switching teams stops the previous audio
- [ ] Transcript, plus pause, resume, and replay; loading/playing/paused/unavailable states
- [ ] Backend ElevenLabs adapter: cache by briefing ID, text fallback, voice IDs from env
- [ ] Tests: selection triggers no API writes; never two audios playing

### Data and memory (PRD §8.2, §14.2)
- [ ] Local script: StatsBomb Open Data + Metrica sample → compact style profiles
- [ ] Load into `style_profiles` (stays well under M0's 512 MB)
- [ ] Vector indexes on `style_profiles` and `coach_experiences` with `namespace` filter
- [ ] Retrieval function for A's scout and coach: `search_styles()`, `search_experiences(namespace, ...)` → **hand to A**
- [ ] Dataset attribution shown in the UI

### Secondary panels and controls (PRD §13.4)
- [ ] Event feed, coach comparison, action timeline, evaluation view
- [ ] Demo controls: start, run batch, inject crash, reset

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
| | | |

## Handoff log (contract changes, newest first)

Record every change to `schemas/` or `api/`, every new endpoint, and
anything the other dev's agent needs to know.

| Date / time | Who | Change | Acked by |
|-------------|-----|--------|----------|
| | | | |
