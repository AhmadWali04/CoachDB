# Rival Coaches --- Agent Definitions

**Purpose:** Define the responsibilities, boundaries, inputs, outputs,
and safety rules for the MVP's agents.

## 1. Agent topology

Each team has its own independent coaching workflow:

``` text
Public Match State + Own Private Coach Memory
                    |
               Match Analyst
                    |
              Tactical Coach
                    |
           Execution / Verification
                    |
             Match Simulator
```

The two teams use the same contracts and capabilities but have separate
coach identities, prompts, and private memory namespaces.

Shared services---not LLM agents: - Match simulator and authoritative
state store. - Recovery controller and worker lease manager. - MongoDB
repository and Vector Search adapter. - Evaluation harness. - ElevenLabs
speech adapter.

Do not create an agent for every small task. Three agent roles per coach
are sufficient for the MVP.

## 2. Global rules for every agent

-   Treat structured simulator state and persisted events as the source
    of truth.
-   Never invent a score, event, player attribute, formation, or action
    result.
-   Distinguish observed facts, hypotheses, predictions, and
    recommendations.
-   Cite event IDs or metric names for match-specific factual claims.
-   Never claim an action succeeded unless its effect is verified.
-   Never write directly to authoritative match state. Use typed service
    interfaces.
-   Return schema-valid JSON for machine-consumed outputs.
-   Do not expose private prompts, hidden reasoning, or private memory
    to the opposing coach.
-   Do not use future match events or evaluator-only information.
-   Keep explanations concise and suitable for a coach.
-   If evidence is insufficient, say so and lower confidence.
-   If a tool or dependency fails, return a bounded error; do not
    fabricate a successful result.

## 3. Match Analyst

**One instance per coach.**

### Mission

Turn first-half structured match data into a concise, evidence-grounded
tactical assessment.

### Inputs

-   Match ID, half, score, and current state version.
-   Own team's structured events and metrics.
-   Opponent's public structured events and metrics.
-   Player/team stamina and availability.
-   Allowed tactical options.

### Responsibilities

1.  Summarize what happened.
2.  Identify up to three strengths and three weaknesses for its team.
3.  Identify up to three opponent patterns or vulnerabilities.
4.  Highlight relevant fatigue/availability concerns.
5.  Cite event IDs or metrics for every factual observation.
6.  Separate evidence from interpretation.

### Must not

-   Submit or execute tactical changes.
-   Claim causation from a small sample without qualification.
-   Access the rival coach's private memory or internal reasoning.
-   Invent events or statistics.

### Output contract

``` json
{
  "match_id": "match_001",
  "team_id": "blue",
  "state_version": 12,
  "summary": "Concise first-half summary.",
  "own_strengths": [
    {
      "observation": "Created chances from the left channel.",
      "evidence": ["event_014", "metric:left_attacks"]
    }
  ],
  "own_weaknesses": [],
  "opponent_patterns": [],
  "fatigue_concerns": [],
  "uncertainties": []
}
```

## 4. Tactical Coach

**One instance per coach.**

### Mission

Choose a valid second-half plan that improves the team's prospects while
anticipating the rival coach.

### Inputs

-   Match Analyst output.
-   Current authoritative match state and allowed tactical capabilities.
-   Retrieved experiences from this coach's private Vector Search
    namespace.
-   Public opponent performance evidence.
-   Match constraints and remaining time.

### Responsibilities

1.  Review the analyst's evidence.
2.  Retrieve relevant past experiences when available.
3.  Identify the most important tactical problem/opportunity.
4.  Predict the rival coach's likely adjustment, with confidence and
    evidence.
5.  Select one coherent tactical plan from the allowed schema.
6.  State expected benefits, risks, and what evidence would indicate
    success.
7.  Produce a concise spoken briefing script for ElevenLabs.

### Decision principles

-   Prefer a small number of coherent changes over changing every
    setting.
-   Do not select unsupported or unavailable actions.
-   Do not assume a retrieved strategy will work identically in a
    different context.
-   Consider fatigue and the trade-off between pressing intensity and
    stamina.
-   Do not optimize only for possession; consider chance creation and
    defensive exposure.
-   If confidence is low, choose a conservative valid plan.

### Output contract

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
  "primary_objective": "Create more chances down the left.",
  "expected_effects": ["More left-side entries"],
  "risks": ["Higher stamina use"],
  "success_indicators": ["Increase in left-channel entries"],
  "rationale": "Concise evidence-based explanation.",
  "voice_script": "We have found space down the left..."
}
```

## 5. Execution and Verification Worker

**One instance per coach.** This may be implemented as deterministic
application code rather than an LLM.

### Mission

Safely apply the coach's approved tactical plan and verify the resulting
simulator state.

### Inputs

-   Validated tactical plan.
-   Match ID, team ID, current state version.
-   Allowed capabilities.
-   Stable action ID.
-   Current worker lease and fencing token.

### Responsibilities

1.  Validate the plan against the current capability schema.
2.  Persist an action record as `proposed`.
3.  Submit the action using a stable idempotency key.
4.  Record `submitted`; do not call this success.
5.  Read the authoritative simulator state.
6.  Confirm the requested settings are active.
7.  Persist `applied` and then `verified` with observed state version.
8.  If the result is uncertain, reconcile before retrying.
9.  Reject or request a replacement for invalid plans.
10. Respect lease/fencing ownership before committing.

### Action statuses

`proposed`, `submitted`, `applied`, `verified`, `rejected`, `failed`,
`unknown`.

### Critical rule

Never retry an `unknown` action blindly. Read current simulator state
and query action status first. Reuse the same action ID on a safe retry.

## 6. Recovery Controller

**Not an LLM agent. Implement as deterministic infrastructure.**

### Mission

Detect failed or stalled workers and resume durable workflows safely.

### Responsibilities

-   Monitor worker heartbeat, lease expiry, and progress.
-   Acquire an expired task using an atomic lease claim.
-   Increment the fencing token on reassignment.
-   Load the latest durable checkpoint.
-   Reconcile actions in `submitted`, `applied`, or `unknown` states
    against the simulator.
-   Skip verified steps.
-   Resume at the first incomplete step.
-   Record recovery attempts and outcomes.

### Must not

-   Assume a missing heartbeat proves a process is dead.
-   Replay verified actions.
-   Allow a worker with an old fencing token to commit.
-   Use LLM-generated guesses to decide whether an external action
    occurred.

## 7. Environment Adaptation

**MVP implementation: deterministic validation plus bounded agent
assistance.**

### Mission

Handle known classes of simulator schema or capability changes safely.

### Supported MVP cases

-   A player becomes unavailable.
-   A requested tactical enum is no longer supported.
-   An optional event field is added or an event schema version changes.

### Workflow

1.  Validate against the current versioned schema/capability list.
2.  Fetch current simulator state and capabilities.
3.  Preserve the original tactical intent.
4.  Map to a safe supported alternative only when the mapping is
    explicit.
5.  Otherwise ask Tactical Coach for a replacement.
6.  Validate, execute, read back, and verify.
7.  Persist the old request, adapted request, reason, schema version,
    and result.

Never silently coerce an invalid instruction.

## 8. Evaluation Harness

**Not an LLM agent. Deterministic evaluator.**

### Mission

Compare coaches fairly using structured data.

### Responsibilities

-   Calculate match outcome and goal difference.
-   Measure first-half to second-half tactical changes.
-   Compare predictions with actual rival decisions.
-   Calculate valid-plan and verified-action rates.
-   Measure recovery correctness and duplicate effects.
-   Measure evidence grounding from cited event IDs.
-   Record latency and model/tool usage.
-   Run repeated seeded matches with teams/sides swapped.

### Fairness constraints

-   Same public information, deadlines, action schema, and comparable
    model/tool budgets.
-   Separate private coach memories.
-   No future information.
-   Do not use win rate as the only measure.

## 9. ElevenLabs Voice Adapter

**Not an agent. External speech service.**

### Mission

Convert approved, persisted coach scripts into audio.

### Inputs

-   Stable briefing ID.
-   Coach/team identity.
-   Persisted voice script.
-   Configured ElevenLabs voice ID.

### Responsibilities

-   Call ElevenLabs text-to-speech.
-   Cache by briefing ID.
-   Return audio reference and metadata.
-   Keep transcript available.
-   Fail gracefully to text if the service is unavailable.

### Must not

-   Generate new tactical advice.
-   Add match facts not present in the persisted script.
-   Block match execution if TTS fails.
-   Store API keys or large audio blobs in MongoDB match documents.

## 10. Agent memory boundaries

  -----------------------------------------------------------------------
  Data                                Access
  ----------------------------------- -----------------------------------
  Public match state/events           Both coaches

  Own team's private coach            That coach only
  experiences                         

  Rival's private experiences         Not accessible

  Rival's submitted public tactical   Available after
  plan                                submission/application, according
                                      to match rules

  Evaluator-only metrics and future   Evaluator only
  events                              
  -----------------------------------------------------------------------

Memory retrieval must be filtered by coach/team namespace. Store
verified outcomes with experiences; do not store an unverified
recommendation as a successful tactic.

## 11. Build order

1.  Implement simulator and typed contracts.
2.  Implement analyst using structured match summaries.
3.  Implement tactical coach with strict JSON schema.
4.  Implement execution and verification as deterministic code.
5.  Duplicate the coach workflow with isolated memory for the rival.
6.  Add MongoDB persistence and recovery controller.
7.  Add Vector Search experience retrieval.
8.  Add evaluator.
9.  Add ElevenLabs voice adapter.
10. Add dashboard.

Keep every role behind a typed interface so models can be swapped
without rewriting the simulator.
