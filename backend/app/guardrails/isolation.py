"""Coach isolation guardrails (PRD §7, AGENTS.md §10).

Rules enforced here:
1. A coach agent's only match input is a `CoachView` from `build_coach_view`.
2. Both coaches decide on the same frozen halftime snapshot.
3. Halftime plans are sealed: neither plan can be read until both are in.
4. Memory reads are limited to the coach's own namespace.
"""

from collections.abc import Iterable

from app.schemas import MatchEvent, MatchPhase, MatchState, TacticalPlan, TeamId
from app.schemas.coach_view import CoachView, PublicPlayer, PublicTeam


class GuardrailViolation(Exception):
    """Raised when code tries to cross the boundary between rival coaches."""


def rival_of(team_id: TeamId) -> TeamId:
    return TeamId.RED if team_id == TeamId.BLUE else TeamId.BLUE


# --- Memory namespaces -------------------------------------------------------


def coach_namespace(team_id: TeamId) -> str:
    return f"coach:{TeamId(team_id).value}"


def require_own_namespace(team_id: TeamId, namespace: str) -> str:
    """Call at the top of every memory read/write made on a coach's behalf."""
    expected = coach_namespace(team_id)
    if namespace != expected:
        raise GuardrailViolation(
            f"coach {team_id} may only use memory namespace {expected!r}, got {namespace!r}"
        )
    return namespace


# --- Coach input --------------------------------------------------------------


def build_coach_view(state: MatchState, events: Iterable[MatchEvent], team_id: TeamId) -> CoachView:
    """Build the halftime input for one coach from authoritative state."""
    if state.phase != MatchPhase.HALFTIME:
        raise GuardrailViolation(f"coach views are built at halftime, not {state.phase}")

    team_id = TeamId(team_id)
    rival_id = rival_of(team_id)
    own = next(t for t in state.teams if t.team_id == team_id)
    rival = next(t for t in state.teams if t.team_id == rival_id)

    return CoachView(
        match_id=state.match_id,
        team_id=team_id,
        rival_team_id=rival_id,
        memory_namespace=coach_namespace(team_id),
        snapshot_state_version=state.state_version,
        phase=state.phase,
        score=state.score,
        stats=state.stats,
        own_team=own,
        rival_team=PublicTeam(
            team_id=rival.team_id,
            name=rival.name,
            coach_name=rival.coach_name,
            side=rival.side,
            # Tactics are fixed for the whole first half (PRD §5.1), so the
            # formation at the halftime snapshot is the kickoff formation.
            kickoff_formation=rival.tactics.formation,
            players=[
                PublicPlayer(
                    player_id=p.player_id,
                    name=p.name,
                    number=p.number,
                    role=p.role,
                    available=p.available,
                )
                for p in rival.players
            ],
        ),
        # First-half events only: nothing produced after the snapshot, and so
        # nothing that could reflect the rival's halftime decision.
        public_events=[e for e in events if e.match_id == state.match_id and e.half == 1],
    )


# --- Sealed halftime plans ------------------------------------------------------


class SealedHalftimePlans:
    """Holds both coaches' plans until both are submitted.

    There is deliberately no way to read a single plan. The orchestrator calls
    `reveal()` once both are in, then applies both plans together.
    """

    def __init__(self, match_id: str, snapshot_state_version: int) -> None:
        self.match_id = match_id
        self.snapshot_state_version = snapshot_state_version
        self._plans: dict[TeamId, TacticalPlan] = {}

    def submit(self, submitter: TeamId, plan: TacticalPlan) -> None:
        submitter = TeamId(submitter)
        if plan.team_id != submitter:
            raise GuardrailViolation(f"coach {submitter} cannot submit a plan for {plan.team_id}")
        if plan.match_id != self.match_id:
            raise GuardrailViolation("plan is for a different match")
        if plan.based_on_state_version != self.snapshot_state_version:
            raise GuardrailViolation(
                f"plan is based on state {plan.based_on_state_version}, "
                f"halftime snapshot is {self.snapshot_state_version}"
            )
        if submitter in self._plans:
            raise GuardrailViolation(f"coach {submitter} already submitted")
        self._plans[submitter] = plan

    def has_submitted(self, team_id: TeamId) -> bool:
        return TeamId(team_id) in self._plans

    @property
    def complete(self) -> bool:
        return len(self._plans) == len(TeamId)

    def reveal(self) -> dict[TeamId, TacticalPlan]:
        if not self.complete:
            missing = [t.value for t in TeamId if t not in self._plans]
            raise GuardrailViolation(f"plans stay sealed until all are in; missing {missing}")
        return dict(self._plans)
