"""Atomic fenced match checkpoints, with idempotent collection projections.

Runtime, state and action ledger commit in one match document. Pending outputs
travel with that checkpoint, so replacement workers can finish publishing them.
"""

from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.persistence import MongoMatchRepository
from app.schemas import CoachDecision, Frame, MatchEvent, MatchState


class LeaseLost(RuntimeError):
    pass


class EngineStore:
    def __init__(self, database, *, now=None):
        self.db, self.repo = database, MongoMatchRepository(database)
        self.now = now or (lambda: datetime.now(UTC))
        self.repo.ensure_indexes()
        self.db.worker_leases.create_index("match_id", unique=True)
        self.db.coach_experiences.create_index("experience_id", unique=True)
        self.db.evaluations.create_index("batch_id", unique=True)

    def create(self, simulator):
        document = simulator.snapshot().model_dump(mode="python")
        document["_engine"] = {
            "runtime": simulator.checkpoint(),
            "fence": 0,
            "lease": {"owner": "", "expires_at": self.now()},
            "actions": {},
            "decisions": {},
            "crash_armed": False,
            "crash_fired": False,
            "recoveries": 0,
            "pending": {"events": [], "frames": []},
            "decision_cutoff": None,
        }
        self.db.matches.insert_one(document)
        return simulator.snapshot()

    def read(self, match_id):
        return self.db.matches.find_one({"match_id": match_id})

    def state(self, match_id):
        document = self.read(match_id)
        if document is None:
            raise KeyError(match_id)
        return MatchState.model_validate({k: document[k] for k in MatchState.model_fields})

    def claim(self, match_id, worker):
        now = self.now()
        doc = self.db.matches.find_one_and_update(
            {
                "match_id": match_id,
                "phase": {"$ne": "full_time"},
                "_engine.lease.expires_at": {"$lte": now},
            },
            {
                "$inc": {"_engine.fence": 1},
                "$set": {
                    "_engine.lease": {"owner": worker, "expires_at": now + timedelta(seconds=15)}
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            self.db.worker_leases.update_one(
                {"match_id": match_id},
                {
                    "$set": {
                        "owner": worker,
                        "fencing_token": doc["_engine"]["fence"],
                        "expires_at": now + timedelta(seconds=15),
                        "heartbeat": now,
                    }
                },
                upsert=True,
            )
        return doc

    def guard(self, match_id, worker, token):
        return {
            "match_id": match_id,
            "_engine.fence": token,
            "_engine.lease.owner": worker,
            "_engine.lease.expires_at": {"$gt": self.now()},
        }

    def heartbeat(self, match_id, worker, token):
        now = self.now()
        result = self.db.matches.update_one(
            self.guard(match_id, worker, token),
            {"$set": {"_engine.lease.expires_at": now + timedelta(seconds=15)}},
        )
        if result.matched_count != 1:
            raise LeaseLost(match_id)
        self.db.worker_leases.update_one(
            {"match_id": match_id, "fencing_token": token},
            {"$set": {"heartbeat": now, "expires_at": now + timedelta(seconds=15)}},
        )

    def commit(self, simulator, worker, token, *, metadata=None):
        state = simulator.snapshot().model_dump(mode="python")
        state["_engine.runtime"] = simulator.checkpoint()
        state["_engine.pending"] = {
            "events": [event.model_dump(mode="python") for event in simulator.state.events],
            "frames": [frame.model_dump(mode="python") for frame in simulator.state.frames],
        }
        for key, value in (metadata or {}).items():
            state[f"_engine.{key}"] = value
        result = self.db.matches.update_one(
            self.guard(simulator.state.match_id, worker, token), {"$set": state}
        )
        if result.matched_count != 1:
            raise LeaseLost(simulator.state.match_id)
        self.publish(self.read(simulator.state.match_id))
        simulator.state.events.clear()
        simulator.state.frames.clear()

    def publish(self, document):
        """A crash after authoritative commit can replay these immutable outputs safely."""
        engine = document["_engine"]
        for event in engine["pending"]["events"]:
            self.repo.append_event(MatchEvent.model_validate(event))
        for frame in engine["pending"]["frames"]:
            self.repo.append_frame(Frame.model_validate(frame))
        for decision in engine["decisions"].values():
            self.repo.save_decision(CoachDecision.model_validate(decision))
        for action in engine["actions"].values():
            try:
                self.db.actions.replace_one(
                    {
                        "action_id": action["action_id"],
                        "fencing_token": {"$lte": action["fencing_token"]},
                    },
                    action,
                    upsert=True,
                )
            except DuplicateKeyError:
                pass  # A newer fenced projection already exists.
        task = {
            "task_id": document["match_id"],
            "match_id": document["match_id"],
            "step": document["phase"],
            "match_state_version": document["state_version"],
            "fencing_token": engine["fence"],
            "checkpoint_at": self.now(),
            "completed_step_ids": ["first_half"] if document["half"] == 2 else [],
            "last_verified_action_id": next(
                (a["action_id"] for a in engine["actions"].values() if a["status"] == "verified"),
                None,
            ),
        }
        try:
            self.db.tasks.replace_one(
                {"task_id": task["task_id"], "fencing_token": {"$lte": task["fencing_token"]}},
                task,
                upsert=True,
            )
        except DuplicateKeyError:
            pass

    def expire(self, match_id, worker, token):
        self.db.matches.update_one(
            self.guard(match_id, worker, token), {"$set": {"_engine.lease.expires_at": self.now()}}
        )

    def arm_crash(self, match_id):
        result = self.db.matches.update_one(
            {
                "match_id": match_id,
                "phase": {"$in": ["first_half", "half_time", "halftime"]},
                "_engine.crash_fired": False,
            },
            {"$set": {"_engine.crash_armed": True}},
        )
        return result.matched_count == 1
