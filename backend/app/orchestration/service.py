"""Match service: runs simulators in the background and persists every step.

The simulator owns match truth; this service only drives it and records what
it produced. Each step is persisted as events, then frames, then the match
state (version-checked), so a reader never sees state ahead of its frames.

Halftime is delegated to a `HalftimeHandler` (the coaches). Without one, the
second half starts with first-half tactics.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.schemas import Frame, MatchEvent, MatchPhase, MatchState
from app.simulator import MatchSimulator, new_match_state

logger = logging.getLogger(__name__)


class MatchRepository(Protocol):
    def create_match(self, state: MatchState) -> None: ...
    def get_match(self, match_id: str) -> MatchState | None: ...
    def update_match(self, state: MatchState, *, expected_state_version: int) -> None: ...
    def append_event(self, event: MatchEvent) -> None: ...
    def append_frame(self, frame: Frame) -> None: ...
    def get_frames(self, match_id: str, *, from_seq: int = 0, limit: int = 50) -> list[Frame]: ...
    def get_events(
        self, match_id: str, *, after_event_id: str | None = None, limit: int = 200
    ) -> list[MatchEvent]: ...


class HalftimeHandler(Protocol):
    def __call__(self, run: MatchRun) -> None:
        """Decide and apply both teams' plans, then return. Must not step the match."""
        ...


class UnknownMatch(LookupError):
    pass


@dataclass
class MatchRun:
    """One live match: its simulator plus what the service has persisted."""

    match_id: str
    simulator: MatchSimulator
    repository: MatchRepository
    persisted_version: int = 0
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None
    error: str | None = None

    def persist(self, events: list[MatchEvent], frames: list[Frame]) -> MatchState:
        """Record simulator output, then advance the stored match state."""
        for event in events:
            self.repository.append_event(event)
        for frame in frames:
            self.repository.append_frame(frame)
        state = self.simulator.state
        if state.state_version != self.persisted_version:
            self.repository.update_match(state, expected_state_version=self.persisted_version)
            self.persisted_version = state.state_version
        return state


class MatchService:
    def __init__(
        self,
        repository: MatchRepository,
        *,
        step_seconds: float = 1.0,
        halftime: HalftimeHandler | None = None,
        new_id: Callable[[], str] = lambda: f"match_{uuid.uuid4().hex[:10]}",
    ) -> None:
        self.repository = repository
        self.step_seconds = step_seconds
        self.halftime = halftime
        self._new_id = new_id
        self._runs: dict[str, MatchRun] = {}
        self._lock = threading.Lock()

    # --- lifecycle --------------------------------------------------------------

    def create_match(
        self, seed: int | None = None, steps_per_half: int = 20, *, start: bool = True
    ) -> MatchState:
        seed = seed if seed is not None else int.from_bytes(uuid.uuid4().bytes[:4], "big")
        state = new_match_state(self._new_id(), seed, steps_per_half)
        self.repository.create_match(state)
        run = MatchRun(state.match_id, MatchSimulator(state), self.repository)
        with self._lock:
            self._runs[state.match_id] = run
        if start:
            self._start(run)
        return state

    def reset_match(self, match_id: str) -> MatchState:
        """Stop the match and start a fresh one with the same seed and length."""
        old = self.get_match(match_id)
        self.stop(match_id)
        return self.create_match(old.seed, old.steps_per_half)

    def stop(self, match_id: str) -> None:
        run = self._runs.get(match_id)
        if run is not None:
            run.stop.set()
            if run.thread is not None and run.thread is not threading.current_thread():
                run.thread.join(timeout=5)

    def stop_all(self) -> None:
        for match_id in list(self._runs):
            self.stop(match_id)

    def run(self, match_id: str) -> MatchRun:
        run = self._runs.get(match_id)
        if run is None:
            raise UnknownMatch(match_id)
        return run

    def _start(self, run: MatchRun) -> None:
        run.thread = threading.Thread(
            target=self._loop, args=(run,), name=f"match-{run.match_id}", daemon=True
        )
        run.thread.start()

    # --- driving the simulator ------------------------------------------------------

    def advance(self, run: MatchRun) -> MatchState:
        """One unit of progress: a step, or halftime handling. Used by the loop and tests."""
        with run.lock:
            phase = run.simulator.state.phase
            if phase is MatchPhase.FULL_TIME:
                return run.simulator.state
            if phase is MatchPhase.HALFTIME:
                if self.halftime is not None:
                    self.halftime(run)
                run.persist(run.simulator.drain_pending_events(), [])
                run.simulator.start_second_half()
                return run.persist([], [])
            out = run.simulator.step()
            return run.persist(out.events, out.frames)

    def _loop(self, run: MatchRun) -> None:
        try:
            while not run.stop.is_set():
                started = time.monotonic()
                state = self.advance(run)
                if state.phase is MatchPhase.FULL_TIME:
                    return
                if state.phase is not MatchPhase.HALFTIME:
                    # Persistence time counts toward the step, keeping a steady pace.
                    run.stop.wait(max(0.0, self.step_seconds - (time.monotonic() - started)))
        except Exception as exc:  # keep the API alive; surface the failure on the run
            run.error = type(exc).__name__
            logger.exception("match loop failed", extra={"match_id": run.match_id})

    def run_to_completion(self, match_id: str) -> MatchState:
        run = self.run(match_id)
        state = run.simulator.state
        while state.phase is not MatchPhase.FULL_TIME:
            state = self.advance(run)
        return state

    def wait_for(self, match_id: str, phase: MatchPhase, timeout: float = 10.0) -> MatchState:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.get_match(match_id)
            if state.phase is phase:
                return state
            time.sleep(0.02)
        raise TimeoutError(f"{match_id} did not reach {phase.value}")

    # --- reads (always from the repository) -----------------------------------------

    def get_match(self, match_id: str) -> MatchState:
        state = self.repository.get_match(match_id)
        if state is None:
            raise UnknownMatch(match_id)
        return state
