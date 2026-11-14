from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas import Briefing, CreateMatchRequest, FramesPage, MatchEvent, MatchState, TeamId

from .stubs import NOT_IMPLEMENTED, not_implemented

router = APIRouter(prefix="/matches", tags=["matches"], responses=NOT_IMPLEMENTED)


@router.post("", response_model=MatchState, status_code=201, operation_id="createMatch")
def create_match(body: CreateMatchRequest) -> MatchState:
    raise not_implemented("A")


@router.get("/{match_id}", response_model=MatchState, operation_id="getMatch")
def get_match(match_id: str) -> MatchState:
    raise not_implemented("A")


@router.get("/{match_id}/frames", response_model=FramesPage, operation_id="getFrames")
def get_frames(
    match_id: str,
    from_seq: Annotated[int, Query(ge=0, description="First frame seq to return.")] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FramesPage:
    raise not_implemented("A")


@router.get("/{match_id}/events", response_model=list[MatchEvent], operation_id="getEvents")
def get_events(
    match_id: str,
    after_event_id: Annotated[str | None, Query()] = None,
) -> list[MatchEvent]:
    raise not_implemented("A")


@router.get("/{match_id}/briefings/{team_id}", response_model=Briefing, operation_id="getBriefing")
def get_briefing(match_id: str, team_id: TeamId) -> Briefing:
    """Read-only. Returns the persisted halftime briefing; never generates tactics."""
    raise not_implemented("B")


@router.post("/{match_id}/reset", response_model=MatchState, operation_id="resetMatch")
def reset_match(match_id: str) -> MatchState:
    raise not_implemented("A")
