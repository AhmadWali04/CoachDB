"""Durable halftime workflow with crash recovery (PRD §9).

Worker path (the match loop thread):
    acquire lease (fencing token) -> heartbeat thread -> checkpoint "deciding"
    -> sealed plans (decisions persisted first) -> checkpoint "executing"
    -> for each plan: propose -> submitted -> simulator apply -> applied
       -> read back simulator state -> verified -> checkpoint "done"

Crash injection sits after the simulator applied a plan and before the
ledger recorded it: the worst case, where the effect happened but the worker
never wrote that down. The worker dies, heartbeats stop, the lease expires.

Recovery path (`recover`): claim the expired lease (token + 1), load the
checkpoint, reconcile every open action against the simulator's own record
(`action_result`) before doing anything, then finish the remaining steps.
Verified actions are never repeated; an applied-but-unrecorded action is
marked applied and verified without being sent again.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.schemas import Action, ActionStatus, TacticalPlan, TeamId

from .leases import LeaseLost, LeaseManager
from .ledger import OPEN, ActionLedger

logger = logging.getLogger(__name__)
S = ActionStatus


class WorkerCrash(RuntimeError):
    """Injected crash: the worker process 'dies' at this point."""


def task_id_for(match_id: str) -> str:
    return f"{match_id}:halftime"


def action_id_for(match_id: str, team_id: TeamId) -> str:
    return f"{match_id}:{team_id.value}:halftime"


class HalftimeWorkflow:
    def __init__(
        self,
        decider: Any | None,
        collections: dict[str, Any],
        *,
        lease_ttl_s: float = 3.0,
        heartbeat_s: float = 1.0,
    ) -> None:
        self.decider = decider  # CoachingHalftime, or None for "keep first-half tactics"
        self.leases = LeaseManager(collections["worker_leases"], lease_ttl_s)
        self.ledger = ActionLedger(collections["actions"], self.leases)
        self.tasks = collections["tasks"]
        # Unique keys make lease claims and checkpoints atomic under concurrency.
        collections["worker_leases"].create_index("task_id", unique=True)
        self.tasks.create_index("task_id", unique=True)
        self.ledger.ensure_indexes()
        self.heartbeat_s = heartbeat_s
        self._armed: set[str] = set()
        self._lock = threading.Lock()

    # --- demo control ------------------------------------------------------------

    def arm_crash(self, match_id: str) -> None:
        with self._lock:
            self._armed.add(match_id)

    def _crash_now(self, match_id: str) -> bool:
        with self._lock:
            if match_id in self._armed:
                self._armed.discard(match_id)
                return True
            return False

    # --- worker ---------------------------------------------------------------------

    def __call__(self, run: Any) -> None:
        owner = f"worker-{uuid.uuid4().hex[:6]}"
        task_id = task_id_for(run.match_id)
        token = self.leases.acquire(task_id, owner)
        if token is None:
            raise LeaseLost(f"{task_id} is owned by another worker")
        self._checkpoint(
            task_id,
            match_id=run.match_id,
            status="running",
            step="deciding",
            owner=owner,
            token=token,
            snapshot_state_version=run.simulator.state.state_version,
            recoveries=0,
            resubmissions=0,
            duplicate_effects=0,
        )
        self._run_with_heartbeat(run, task_id, owner, token)

    def _run_with_heartbeat(self, run: Any, task_id: str, owner: str, token: int) -> None:
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(self.heartbeat_s):
                try:
                    self.leases.heartbeat(task_id, owner, token)
                except LeaseLost:
                    return

        beater = threading.Thread(target=beat, name=f"heartbeat-{task_id}", daemon=True)
        beater.start()
        try:
            self._work(run, task_id, owner, token)
        finally:
            stop.set()  # a crashed worker stops heartbeating too

    def _work(self, run: Any, task_id: str, owner: str, token: int) -> None:
        task = self.tasks.find_one({"task_id": task_id})
        version = task["snapshot_state_version"]
        plans = self.decider.decide(run, version) if self.decider else {}
        self.leases.require(task_id, token)
        self._checkpoint(task_id, step="executing")
        for team in sorted(plans):
            self._execute(run, team, plans[team], task_id, token)
        self._checkpoint(task_id, step="done", status="done")
        self.leases.release(task_id, owner, token)

    def _execute(
        self, run: Any, team: TeamId, plan: TacticalPlan, task_id: str, token: int
    ) -> None:
        action_id = action_id_for(run.match_id, team)
        now = datetime.now(UTC)
        action = self.ledger.propose(
            Action(
                action_id=action_id,
                match_id=run.match_id,
                team_id=team,
                requested=plan.plan,
                expected_state_version=plan.based_on_state_version,
                status=S.PROPOSED,
                fencing_token=token,
                created_at=now,
                updated_at=now,
            ),
            task_id,
        )
        if action.status not in OPEN:
            return  # verified/rejected/failed earlier: never repeat it
        sim = run.simulator
        # Submitted by an earlier (crashed) worker, so its fate is uncertain.
        inherited = action.status in (S.SUBMITTED, S.UNKNOWN)
        if action.status is S.PROPOSED:
            action = self.ledger.transition(action_id, S.SUBMITTED, task_id=task_id, token=token)

        if action.status in (S.SUBMITTED, S.UNKNOWN):
            # Reconcile first: did the simulator already apply this action?
            result = sim.action_result(action_id)
            if result is None:
                if inherited:
                    self._checkpoint(task_id, inc={"resubmissions": 1})
                result = sim.apply_tactics(action_id, team, plan.plan, plan.based_on_state_version)
                if self._crash_now(run.match_id):
                    raise WorkerCrash(f"injected after applying {action_id}, before recording it")
            if not result.applied:
                self.ledger.transition(
                    action_id,
                    S.REJECTED,
                    task_id=task_id,
                    token=token,
                    simulator_ref=result.reason,
                )
                return
            action = self.ledger.transition(
                action_id, S.APPLIED, task_id=task_id, token=token, simulator_ref=action_id
            )

        if action.status is S.APPLIED:
            observed = sim.team(team).tactics
            if observed != plan.plan:
                self.ledger.transition(action_id, S.FAILED, task_id=task_id, token=token)
                return
            changes = sim.effects_of(action_id)
            if changes > 1:
                self._checkpoint(task_id, inc={"duplicate_effects": changes - 1})
            self.ledger.transition(
                action_id,
                S.VERIFIED,
                task_id=task_id,
                token=token,
                observed_state_version=sim.state.state_version,
            )

    # --- recovery -------------------------------------------------------------------------

    def needs_recovery(self, match_id: str) -> bool:
        task = self.tasks.find_one({"task_id": task_id_for(match_id)})
        return (
            task is not None
            and task.get("status") == "running"
            and self.leases.expired(task_id_for(match_id))
        )

    def recover(self, run: Any) -> bool:
        """Take over an abandoned halftime. True if this call finished it."""
        task_id = task_id_for(run.match_id)
        owner = f"recovery-{uuid.uuid4().hex[:6]}"
        token = self.leases.acquire(task_id, owner)
        if token is None:
            return False
        logger.warning("recovering halftime", extra={"task_id": task_id, "token": token})
        self._checkpoint(task_id, owner=owner, token=token, inc={"recoveries": 1})
        self._run_with_heartbeat(run, task_id, owner, token)
        return True

    def task(self, match_id: str) -> dict | None:
        doc = self.tasks.find_one({"task_id": task_id_for(match_id)})
        return {k: v for k, v in doc.items() if k != "_id"} if doc else None

    def _checkpoint(self, task_id: str, *, inc: dict | None = None, **fields: Any) -> None:
        update: dict[str, Any] = {"$set": {**fields, "updated_at": datetime.now(UTC)}}
        if inc:
            update["$inc"] = inc
        self.tasks.find_one_and_update({"task_id": task_id}, update, upsert=True)
