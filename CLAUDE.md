# CLAUDE.md --- Rival Coaches

## Project mission

Build **Rival Coaches**, a hackathon MVP where two independent AI soccer
coaching systems compete in a seeded, simplified soccer simulation.

Each coach analyzes the first half, predicts the opposing coach's likely
tactical adjustment, and submits a structured halftime plan. The
simulator applies those plans and generates the second half. MongoDB
Atlas stores verified state, action history, checkpoints, and coach
experiences. Atlas Vector Search retrieves relevant prior experiences. A
recovery controller resumes interrupted work safely. ElevenLabs
generates optional spoken halftime briefings.

Read `PRD.md` and `AGENTS.md` before making architectural changes. These
documents define product scope and agent contracts.

## Highest-priority engineering rules

1.  **The simulator is the source of match truth.** LLMs analyze and
    recommend; they do not invent or directly mutate match facts.
2.  **No free-form LLM output controls the simulator.** Validate every
    plan against typed schemas and allowed capabilities.
3.  **A sent action is not a completed action.** Only mark it `verified`
    after reading back authoritative simulator state.
4.  **Never blindly retry an uncertain action.** Reconcile state first
    and use stable idempotency keys.
5.  **MongoDB is durable application state.** Process memory,
    conversation history, and LLM context are not authoritative.
6.  **Keep coaches independent.** Separate prompts, identity, and memory
    namespaces.
7.  **The evaluator is independent and deterministic.** Do not let
    either coach grade itself.
8.  **ElevenLabs is optional presentation.** TTS failure must never stop
    a match.
9.  **Build the smallest working end-to-end demo first.** Do not add
    unrequested infrastructure or features.
10. **Prefer simple, typed, testable code over abstractions created for
    hypothetical future scale.**

## Before coding

1.  Inspect the existing repository and identify its language,
    framework, entry points, tests, and conventions.
2.  Read the PRD and agent definitions.
3.  Write a short implementation plan with files to add/change.
4.  Identify existing functionality to preserve.
5.  Do not replace the project structure or dependencies without a
    concrete reason.
6.  If a requirement is ambiguous, choose the smallest option consistent
    with the PRD and document the assumption. Ask only when the
    ambiguity blocks safe implementation.

## Target architecture

``` text
React + TypeScript UI
        |
     FastAPI
        |
 Match Orchestrator / LangGraph
    /                 \
Blue Coach          Red Coach
Analyst              Analyst
Tactical Coach       Tactical Coach
Executor             Executor
    \                 /
     Soccer Simulator
           |
   Action Verification
           |
      MongoDB Atlas
           |
 Recovery Controller

Atlas Vector Search -> coach experience retrieval
ElevenLabs           -> voice briefing audio
Evaluation Harness   -> independent metrics
```

Do not introduce a separate graph database for this MVP. The knowledge
required here is structured match/event/action/experience data in
MongoDB collections plus vector retrieval.

## Suggested repository layout

Adapt to the repository if it already has a sensible structure. Do not
create duplicate application roots.

``` text
.
├── CLAUDE.md
├── PRD.md
├── AGENTS.md
├── .env.example
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── config/
│   │   ├── schemas/
│   │   ├── simulator/
│   │   ├── coaches/
│   │   ├── orchestration/
│   │   ├── persistence/
│   │   ├── recovery/
│   │   ├── evaluation/
│   │   └── voice/
│   └── tests/
└── frontend/
    └── ...
```

## Implementation sequence

Work in small, testable phases. Do not jump ahead while an earlier phase
is broken.

### Phase 0 --- Repository and contracts

-   Inspect repo and report current state.
-   Define typed models for teams, players, match state, events,
    tactical plans, actions, tasks, and coach decisions.
-   Add environment configuration and `.env.example`.
-   Add MongoDB repository interface and health check.
-   Add schema validation tests.

**Done when:** app starts, schemas validate, and a test match record can
be persisted and read.

### Phase 1 --- Deterministic soccer simulator

-   Implement seeded simulation.
-   Support two teams and a compact player/team model.
-   Implement match clock, first half, halftime, second half, full time.
-   Generate structured events and basic statistics.
-   Ensure tactical settings affect event probabilities/outcomes.
-   Keep the simulation explainable and testable; do not claim
    professional realism.

**Done when:** identical seed/config produces reproducible results and a
complete match can run without an LLM.

### Phase 2 --- Two independent coaches

-   Implement Match Analyst and Tactical Coach interfaces.
-   Use structured match summaries, not raw chat transcripts.
-   Require strict typed JSON output.
-   Validate enums, team IDs, state version, confidence, and evidence
    references.
-   Add rival prediction.
-   Give each coach a separate memory namespace.
-   Apply plans only at halftime.

**Done when:** both coaches produce valid plans, can produce different
decisions, and the simulator's second-half behaviour responds to those
decisions.

### Phase 3 --- Durable state and crash recovery

-   Persist events, task checkpoints, decisions, and action lifecycle.
-   Implement action IDs and simulator-side idempotency.
-   Implement worker heartbeats, leases, and fencing tokens.
-   Implement recovery controller.
-   Add a crash injection test after action submission but before
    verification.
-   Reconcile against actual simulator state before resuming.

**Done when:** the system recovers without replaying verified work or
duplicating a tactical effect.

### Phase 4 --- Vector Search and bounded adaptation

-   Store coach experiences with verified outcomes and embeddings.
-   Add Atlas Vector Search retrieval filtered by coach namespace and
    metadata.
-   Treat retrieval as context, not ground truth.
-   Add versioned simulator capability/schema validation.
-   Handle unavailable player, unsupported tactical option, and changed
    optional event field.
-   Record original intent and any adapted action.

**Done when:** relevant experience can be retrieved and at least one
simulated environment change is handled safely.

### Phase 5 --- Evaluation, ElevenLabs, UI

-   Implement deterministic evaluator and repeated seeded/side-swapped
    matches.
-   Add halftime voice script and ElevenLabs TTS adapter.
-   Cache audio by stable briefing ID.
-   Add text transcript and fallback when TTS is unavailable.
-   Build dashboard for match, coach comparison, action timeline,
    recovery, and evaluation.

**Done when:** a judge can run the end-to-end demo and see/hear the
result.

## Required data contracts

Use a single source of truth for enums and typed schemas. Avoid
duplicating literal allowed values across files.

### Tactical plan

``` json
{
  "match_id": "match_001",
  "team_id": "blue",
  "based_on_state_version": 12,
  "plan": {
    "formation": "4-2-3-1",
    "mentality": "attacking",
    "pressing": "high",
    "defensive_line": "medium",
    "attack_focus": "left",
    "tempo": "fast"
  },
  "opponent_prediction": {
    "likely_change": "lower defensive line",
    "confidence": 0.72,
    "evidence": ["event_014"]
  },
  "rationale": "Evidence-based short explanation.",
  "risks": ["Higher stamina use"],
  "success_indicators": ["Increase in left-channel entries"],
  "voice_script": "We have found space down the left..."
}
```

### Action lifecycle

Allowed states:

`proposed → submitted → applied → verified`

Other terminal/exception states:

`rejected`, `failed`, `unknown`.

Persist: - Stable `action_id`. - Match/team IDs. - Requested plan. -
Expected state version. - Current status. - Simulator
response/reference. - Verified observed state/version. - Worker fencing
token. - Created/updated timestamps.

### Checkpoint

Persist: - Task/workflow ID. - Match/team/coach IDs. - Workflow step. -
Completed step IDs. - Pending step IDs. - Last verified action ID. -
Match state version. - Checkpoint timestamp.

Do not serialize hidden chain-of-thought. Persist concise summaries,
evidence references, decisions, and execution state.

## MongoDB collection guidance

Use these collections unless the existing project already has an
equivalent design:

-   `matches`
-   `match_events`
-   `coach_decisions`
-   `tasks`
-   `actions`
-   `coach_experiences`
-   `worker_leases`

Add unique indexes for stable IDs and query indexes for match,
team/coach namespace, status, and timestamps. Keep match events
append-only. Keep audio outside match documents; store an audio
reference and metadata.

Do not assume MongoDB and an external simulator can participate in one
atomic transaction. Use an action ledger, idempotency, and
read-after-write verification.

## ElevenLabs requirements

-   Read API key and voice IDs from environment variables.
-   Never commit secrets or real credentials.
-   Generate audio only from a persisted, approved `voice_script`.
-   Cache by briefing ID to avoid duplicate TTS requests.
-   Store audio in suitable object/file storage; MongoDB stores
    metadata/reference.
-   Always show the text transcript.
-   If ElevenLabs errors or times out, continue with text only.
-   TTS must not control tactics or alter match state.

Expected environment variables (names may be adapted to existing
conventions):

``` env
MONGODB_URI=
MONGODB_DATABASE=rival_coaches
LLM_PROVIDER=
LLM_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_BLUE_VOICE_ID=
ELEVENLABS_RED_VOICE_ID=
```

Do not print secret values in logs.

## Testing requirements

Write tests as features are implemented. At minimum:

1.  Same seed/config gives same simulation output.
2.  Invalid tactical enum is rejected.
3.  Tactical plan changes second-half simulation parameters.
4.  Duplicate action ID does not apply an action twice.
5.  Submitted-but-unverified action is reconciled against simulator
    state.
6.  Verified action is not replayed after recovery.
7.  Expired lease can be claimed and old fencing token cannot commit.
8.  Coaches cannot retrieve each other's private experiences.
9.  Vector Search outage does not stop a match.
10. Unsupported capability triggers safe adaptation or explicit
    rejection.
11. ElevenLabs failure falls back to text.
12. Evaluator results are reproducible for the same seeds/configuration.

Use mocks/fakes for LLM, MongoDB, and ElevenLabs in unit tests. Keep a
small integration test for real configured services, but never make the
entire test suite depend on external API availability.

## UI requirements

MVP dashboard sections: - Match: pitch/player markers, score, clock,
possession, shots, recent events. - Coaches: side-by-side analysis,
rival prediction, tactical plan, voice player/transcript. - Timeline:
decisions, action lifecycle, verification, recovery. - Evaluation:
repeated match results and metric comparison. - Controls: start match,
run batch, inject crash, reset.

Avoid complex animation until core match, persistence, and recovery
flows work.

## Coding standards

-   Use explicit types and schema validation at boundaries.
-   Keep simulation logic deterministic and independent of LLM calls.
-   Keep provider integrations behind small interfaces/adapters.
-   Keep prompts in version-controlled files or clearly named constants.
-   Add timeouts and bounded retries to external calls.
-   Log IDs and state transitions, not secrets or private reasoning.
-   Use structured logs with `match_id`, `task_id`, `action_id`,
    `coach_id`, and `state_version`.
-   Make errors actionable; never swallow failures silently.
-   Avoid unnecessary abstractions, microservices, queues, or
    dependencies for the MVP.
-   Run formatter, linter, type checks, and tests after each meaningful
    change.

## Working protocol for Claude Code

For each task: 1. State the phase and specific goal. 2. Inspect relevant
files before editing. 3. Make the smallest coherent change. 4.
Add/update tests. 5. Run relevant tests and report exact results. 6.
Summarize files changed, decisions, and remaining risks. 7. Do not claim
a test passed unless it was actually run. 8. Do not start the next phase
automatically if the current phase has failing tests.

When asked to implement a feature, implement it---not merely describe
how to implement it. If a required external credential is missing, build
and test the adapter with a mock and document the exact environment
variable needed.

## Explicitly avoid

-   Overbuilding a realistic 3D soccer game.
-   Adding live sports data feeds.
-   Letting LLMs generate the actual play-by-play state.
-   One giant agent with an unstructured prompt.
-   Letting agents write directly to MongoDB collections without
    repository/service validation.
-   Treating heartbeat as proof of task progress.
-   Blind retries after uncertain actions.
-   Shared private memory between rival coaches.
-   Letting ElevenLabs failure block the match.
-   Adding Neo4j, Kafka, Kubernetes, or extra infrastructure unless a
    demonstrated MVP requirement demands it.
