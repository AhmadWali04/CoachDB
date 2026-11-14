"""Seeded, side-swapped evaluation batches over the real match pipeline.

Each seed runs twice: normal sides, then swapped (teams switch ends and the
other team kicks off), to reduce starting-side bias (PRD §12). Matches run
without step delays; with AI coaches each halftime still calls the model.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from app.execution import action_id_for
from app.orchestration.service import MatchService
from app.schemas import MatchPhase, TeamId
from app.schemas.evaluation import EvaluationBatch

from .evaluator import MatchRecords, coach_metrics, match_result

logger = logging.getLogger(__name__)

NOTES = [
    "Metrics are reported per coach; wins alone do not rank coaches (PRD §12).",
    "Prediction accuracy is a keyword heuristic over the predicted change.",
    "The simulator is a simplified tactical model, not a realistic football model.",
]


class EvaluationRunner:
    def __init__(self, service: MatchService) -> None:
        self.service = service
        self._batches: dict[str, EvaluationBatch] = {}
        self._lock = threading.Lock()

    def get(self, batch_id: str) -> EvaluationBatch | None:
        with self._lock:
            return self._batches.get(batch_id)

    def start(self, seeds: list[int], steps_per_half: int, *, background: bool = True) -> str:
        batch_id = f"eval_{uuid.uuid4().hex[:8]}"
        self._store(
            EvaluationBatch(
                batch_id=batch_id,
                status="running",
                seeds=seeds,
                steps_per_half=steps_per_half,
                results=[],
                metrics={},
                notes=NOTES,
            )
        )
        if background:
            threading.Thread(
                target=self._run,
                args=(batch_id, seeds, steps_per_half),
                daemon=True,
                name=batch_id,
            ).start()
        else:
            self._run(batch_id, seeds, steps_per_half)
        return batch_id

    def _store(self, batch: EvaluationBatch) -> None:
        with self._lock:
            self._batches[batch.batch_id] = batch

    def _run(self, batch_id: str, seeds: list[int], steps_per_half: int) -> None:
        records: list[MatchRecords] = []
        try:
            for seed in seeds:
                for swapped in (False, True):
                    records.append(self._play(seed, steps_per_half, swapped))
                    self._publish(batch_id, records, "running")
            self._publish(batch_id, records, "done")
        except Exception:
            logger.exception("evaluation batch failed", extra={"batch_id": batch_id})
            self._publish(batch_id, records, "failed")

    def _play(self, seed: int, steps_per_half: int, swapped: bool) -> MatchRecords:
        svc = self.service
        state = svc.create_match(seed, steps_per_half, start=False, swap_sides=swapped)
        final = svc.run_to_completion(state.match_id)
        if final.phase is not MatchPhase.FULL_TIME:
            raise RuntimeError("match did not finish")
        run = svc.run(state.match_id)
        halftime: Any = svc.halftime
        ledger = getattr(halftime, "ledger", None)
        decider = getattr(halftime, "decider", halftime)
        return MatchRecords(
            state=final,
            events=svc.repository.get_events(state.match_id, limit=200),
            decisions={t: svc.repository.get_latest_decision(state.match_id, t) for t in TeamId},
            actions=ledger.for_match(state.match_id) if ledger else [],
            effects={
                action_id_for(state.match_id, t): run.simulator.effects_of(
                    action_id_for(state.match_id, t)
                )
                for t in TeamId
            },
            latency_ms=getattr(decider, "latency_ms", {}).get(state.match_id, {}),
            sides_swapped=swapped,
        )

    def _publish(self, batch_id: str, records: list[MatchRecords], status: str) -> None:
        batch = self.get(batch_id)
        self._store(
            batch.model_copy(
                update={
                    "status": status,
                    "results": [match_result(r) for r in records],
                    "metrics": {t: coach_metrics(records, t) for t in TeamId} if records else {},
                }
            )
        )
