from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.orchestration import MatchService, UnknownMatch
from app.orchestration.dependencies import get_match_service
from app.schemas import (
    Briefing,
    CreateMatchRequest,
    ErrorResponse,
    FramesPage,
    MatchEvent,
    MatchPhase,
    MatchState,
    TeamId,
)
from app.voice import BriefingNotFoundError, BriefingService, get_briefing_service

router = APIRouter(
    prefix="/matches",
    tags=["matches"],
    responses={404: {"model": ErrorResponse, "description": "Unknown match"}},
)

Service = Annotated[MatchService, Depends(get_match_service)]


def _not_found(match_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown match {match_id}")


@router.post("", response_model=MatchState, status_code=201, operation_id="createMatch")
def create_match(body: CreateMatchRequest, service: Service) -> MatchState:
    """Create a match and start simulating it in the background."""
    return service.create_match(body.seed, body.steps_per_half)


@router.get("/{match_id}", response_model=MatchState, operation_id="getMatch")
def get_match(match_id: str, service: Service) -> MatchState:
    try:
        return service.get_match(match_id)
    except UnknownMatch as exc:
        raise _not_found(match_id) from exc


@router.get("/{match_id}/frames", response_model=FramesPage, operation_id="getFrames")
def get_frames(
    match_id: str,
    from_seq: Annotated[int, Query(ge=0, description="First frame seq to return.")] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    *,
    service: Service,
) -> FramesPage:
    try:
        state = service.get_match(match_id)
    except UnknownMatch as exc:
        raise _not_found(match_id) from exc
    frames = service.repository.get_frames(match_id, from_seq=from_seq, limit=limit)
    finished = state.phase is MatchPhase.FULL_TIME
    # Always hand back where to continue after a page with frames; null only
    # once the match is over and nothing newer exists.
    next_seq = frames[-1].seq + 1 if frames else (None if finished else from_seq)
    return FramesPage(match_id=match_id, frames=frames, next_seq=next_seq, phase=state.phase)


@router.get("/{match_id}/events", response_model=list[MatchEvent], operation_id="getEvents")
def get_events(
    match_id: str,
    after_event_id: Annotated[str | None, Query()] = None,
    *,
    service: Service,
) -> list[MatchEvent]:
    try:
        service.get_match(match_id)
        return service.repository.get_events(match_id, after_event_id=after_event_id)
    except UnknownMatch as exc:
        raise _not_found(match_id) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{match_id}/briefings/{team_id}", response_model=Briefing, operation_id="getBriefing")
def get_briefing(
    match_id: str,
    team_id: TeamId,
    briefings: Annotated[BriefingService, Depends(get_briefing_service)],
) -> Briefing:
    """Read-only. Returns the persisted halftime briefing; never generates tactics."""
    try:
        return briefings.get_briefing(match_id, team_id)
    except BriefingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{match_id}/reset", response_model=MatchState, operation_id="resetMatch")
def reset_match(match_id: str, service: Service) -> MatchState:
    """Stop this match and start a fresh one with the same seed (new match_id)."""
    try:
        return service.reset_match(match_id)
    except UnknownMatch as exc:
        raise _not_found(match_id) from exc
