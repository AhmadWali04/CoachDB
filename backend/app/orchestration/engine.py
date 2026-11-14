"""Durable match worker, lease heartbeat, sealed decisions and verified execution."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo.errors import PyMongoError

from app.coaches import CoachWorkflow
from app.coaches.workflow import balanced
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector
from app.guardrails import (
    SealedHalftimePlans,
    build_coach_view,
    coach_namespace,
    require_own_namespace,
)
from app.schemas import Action, CoachDecision, MatchPhase, ObservedTactics, TeamId
from app.simulator import MatchSimulator

from .store import EngineStore, LeaseLost

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, database, settings, *, checkpointer=None):
        self.db, self.settings = database, settings
        self.store = EngineStore(database)
        self.checkpointer = checkpointer or MongoDBSaver(database.client, db_name=database.name)
        self.stop_event = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="match")
        self.monitor = None
        self.active = set()
        self.lock = threading.Lock()

    def create(self, seed, steps=20, *, sides_swapped=False, fast=False):
        match_id = f"match_{uuid4().hex}"
        sim = MatchSimulator(
            match_id,
            seed,
            balanced(),
            balanced(),
            steps,
            started_at=datetime.now(UTC),
            sides_swapped=sides_swapped,
        )
        state = self.store.create(sim)
        self.db.matches.update_one({"match_id": match_id}, {"$set": {"_engine.fast": fast}})
        return state

    def start(self):
        if self.monitor is None:
            self.monitor = threading.Thread(
                target=self._monitor, daemon=True, name="match-recovery"
            )
            self.monitor.start()

    def close(self):
        self.stop_event.set()
        if self.monitor:
            self.monitor.join(timeout=2)
        self.pool.shutdown(wait=True, cancel_futures=True)

    def _monitor(self):
        while not self.stop_event.is_set():
            try:
                for doc in self.db.matches.find(
                    {
                        "phase": {"$ne": "full_time"},
                        "_engine.lease.expires_at": {"$lte": self.store.now()},
                    }
                ):
                    with self.lock:
                        if doc["match_id"] in self.active or len(self.active) >= 4:
                            continue
                        self.active.add(doc["match_id"])
                    self.pool.submit(self._background, doc["match_id"])
            except PyMongoError:
                logger.warning("recovery scan unavailable")
            self.stop_event.wait(0.25)

    def _background(self, match_id):
        try:
            self.run(match_id)
        except Exception:
            logger.exception("match worker stopped", extra={"match_id": match_id})
        finally:
            with self.lock:
                self.active.discard(match_id)

    def run(self, match_id):
        worker = uuid4().hex
        document = self.store.claim(match_id, worker)
        if document is None:
            return
        token = document["_engine"]["fence"]
        done = threading.Event()

        def heartbeat():
            while not done.wait(2):
                try:
                    self.store.heartbeat(match_id, worker, token)
                except (LeaseLost, PyMongoError):
                    return

        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        try:
            self.store.publish(document)
            sim = MatchSimulator.restore(document["_engine"]["runtime"])
            metadata = document["_engine"]
            actions = metadata["actions"]
            if token > 1:
                metadata["recoveries"] += 1
                for action in actions.values():
                    if action["status"] != "verified":
                        action["fencing_token"] = token
                self.store.commit(
                    sim,
                    worker,
                    token,
                    metadata={"recoveries": metadata["recoveries"], "actions": actions},
                )
            while not self.stop_event.is_set():
                if sim.phase == MatchPhase.HALFTIME:
                    cutoff = metadata["decision_cutoff"] or datetime.now(UTC)
                    metadata["decision_cutoff"] = cutoff
                    self.store.commit(sim, worker, token, metadata={"decision_cutoff": cutoff})
                    if not metadata["decisions"]:
                        views = {
                            t: build_coach_view(
                                sim.snapshot(), self.store.repo.get_events(match_id), t
                            )
                            for t in TeamId
                        }
                        decisions = {}
                        latencies = {}
                        for team in TeamId:
                            started = time.perf_counter()
                            decision = CoachWorkflow(
                                team, self.checkpointer, self.db, self.settings
                            ).run(views[team], cutoff)
                            decisions[team.value] = decision.model_dump(mode="python")
                            latencies[team.value] = (time.perf_counter() - started) * 1000
                        metadata["decisions"] = decisions
                        self.store.commit(
                            sim,
                            worker,
                            token,
                            metadata={"decisions": decisions, "decision_latency_ms": latencies},
                        )
                    decisions = {
                        TeamId(t): CoachDecision.model_validate(d)
                        for t, d in metadata["decisions"].items()
                    }
                    sealed = SealedHalftimePlans(match_id, sim.snapshot().state_version)
                    for team, decision in decisions.items():
                        sealed.submit(team, decision.plan)
                    plans = sealed.reveal()
                    if not actions:
                        now = datetime.now(UTC)
                        for team, plan in plans.items():
                            action = Action(
                                action_id=f"{match_id}:{team}:halftime",
                                match_id=match_id,
                                team_id=team,
                                requested=plan.plan,
                                expected_state_version=sim.snapshot().state_version,
                                status="proposed",
                                fencing_token=token,
                                created_at=now,
                                updated_at=now,
                            )
                            actions[team.value] = action.model_dump(mode="python")
                        self.store.commit(sim, worker, token, metadata={"actions": actions})
                    for action in actions.values():
                        if action["status"] == "proposed":
                            action["status"], action["updated_at"] = "submitted", datetime.now(UTC)
                    self.store.commit(sim, worker, token, metadata={"actions": actions})
                    sim.apply_plans(
                        {t: p.plan for t, p in plans.items()},
                        {t: actions[t.value]["action_id"] for t in TeamId},
                    )
                    self.store.commit(sim, worker, token)
                    fresh = self.store.read(match_id)["_engine"]
                    if fresh["crash_armed"] and not fresh["crash_fired"]:
                        self.store.commit(
                            sim, worker, token, metadata={"crash_armed": False, "crash_fired": True}
                        )
                        self.store.expire(match_id, worker, token)
                        return  # deliberate worker death after submit/effect, before verification

                if actions and any(a["status"] != "verified" for a in actions.values()):
                    observed = self.store.state(match_id)
                    for action in actions.values():
                        if action["status"] == "verified":
                            continue
                        team = next(t for t in observed.teams if t.team_id == action["team_id"])
                        if (
                            action["action_id"] not in sim.applied_actions
                            or team.tactics.model_dump(mode="json") != action["requested"]
                            or observed.state_version <= action["expected_state_version"]
                        ):
                            raise ValueError(
                                "uncertain action must reconcile against simulator before retry"
                            )
                        action["status"] = "applied"
                        action["simulator_ref"] = (
                            f"authoritative:v{observed.state_version};fence:{token}"
                        )
                    self.store.commit(sim, worker, token, metadata={"actions": actions})
                    # A fresh authoritative read, never the command response, establishes success.
                    verified = self.store.state(match_id)
                    for action in actions.values():
                        action["status"], action["observed_state_version"] = (
                            "verified",
                            verified.state_version,
                        )
                        action["updated_at"] = datetime.now(UTC)
                    self.store.commit(sim, worker, token, metadata={"actions": actions})

                if sim.phase == MatchPhase.FULL_TIME:
                    self.remember(sim.snapshot(), actions)
                    return
                sim.advance()
                self.store.commit(sim, worker, token)
                self.stop_event.wait(
                    0
                    if document["_engine"].get("fast")
                    else max(0, self.settings.engine_step_seconds)
                )
        finally:
            done.set()
            pulse.join(timeout=3)
            self.store.expire(match_id, worker, token)

    def remember(self, state, actions):
        if len(actions) != 2 or any(a["status"] != "verified" for a in actions.values()):
            return
        for team in state.teams:
            namespace = require_own_namespace(team.team_id, coach_namespace(team.team_id))
            key = f"{state.match_id}:{team.team_id}:experience"
            vector = style_query_vector(ObservedTactics(**team.tactics.model_dump()))
            self.db.coach_experiences.update_one(
                {"experience_id": key},
                {
                    "$setOnInsert": {
                        "experience_id": key,
                        "namespace": namespace,
                        "verified": True,
                        "summary": (
                            f"Verified {team.tactics.formation} {team.tactics.mentality} plan."
                        ),
                        "verified_outcome": f"Final score blue {state.score.blue}, "
                        f"red {state.score.red}; "
                        f"{state.stats[team.team_id].shots} shots.",
                        "occurred_at": datetime.now(UTC),
                        "embedding_model": EMBEDDING_MODEL,
                        "embedding": vector,
                        "dimensions": DIMENSIONS,
                    }
                },
                upsert=True,
            )

    def batch(self, request):
        from app.schemas.evaluation import CoachMetrics, EvaluationBatch

        batch_id = f"batch_{uuid4().hex}"
        batch = EvaluationBatch(
            batch_id=batch_id, status="running", metrics={t: CoachMetrics() for t in TeamId}
        )
        self.db.evaluations.insert_one(batch.model_dump(mode="python"))
        threading.Thread(target=self._batch, args=(batch_id, request), daemon=True).start()
        return batch

    def _batch(self, batch_id, request):
        from app.evaluation.harness import evaluate
        from app.schemas.evaluation import EvaluationBatch, MatchResult

        # Reproducible tactical inputs; live provider latency/outputs are not deterministic.
        trials = Engine(
            self.db,
            self.settings.model_copy(
                update={"llm_provider": "deterministic", "engine_step_seconds": 0}
            ),
            checkpointer=self.checkpointer,
        )
        results, documents, events = [], [], {}
        try:
            for seed in request.seeds:
                for swapped in (False, True):
                    state = trials.create(
                        seed, request.steps_per_half, sides_swapped=swapped, fast=True
                    )
                    while trials.store.state(state.match_id).phase != MatchPhase.FULL_TIME:
                        trials.run(state.match_id)
                        if self.stop_event.wait(0.01):
                            raise RuntimeError("batch stopped")
                    doc = trials.store.read(state.match_id)
                    documents.append(doc)
                    events[state.match_id] = trials.store.repo.get_events(state.match_id)
                    results.append(
                        MatchResult(
                            match_id=state.match_id,
                            seed=seed,
                            sides_swapped=swapped,
                            score=doc["score"],
                        )
                    )
            result = EvaluationBatch(
                batch_id=batch_id,
                status="complete",
                results=results,
                metrics=evaluate(documents, events),
            )
            self.db.evaluations.replace_one(
                {"batch_id": batch_id}, result.model_dump(mode="python")
            )
        except Exception:
            logger.exception("evaluation batch stopped", extra={"batch_id": batch_id})
            self.db.evaluations.update_one({"batch_id": batch_id}, {"$set": {"status": "failed"}})
        finally:
            trials.close()
