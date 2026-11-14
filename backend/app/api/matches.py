import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.orchestration.dependencies import get_engine
from app.orchestration.engine import Engine
from app.schemas import (
    Action,
    Briefing,
    CoachDecision,
    CreateMatchRequest,
    FramesPage,
    MatchEvent,
    MatchState,
    TeamId,
)
from app.voice import BriefingNotFoundError, BriefingService, get_briefing_service

router = APIRouter(prefix="/matches", tags=["matches"])
Worker = Annotated[Engine, Depends(get_engine)]


def require_match(engine, match_id):
    try:
        return engine.store.state(match_id)
    except KeyError as error:
        raise HTTPException(404, "Match not found") from error


@router.post("", response_model=MatchState, status_code=201, operation_id="createMatch")
def create_match(body: CreateMatchRequest, engine: Worker):
    return engine.create(
        body.seed if body.seed is not None else secrets.randbelow(2**31), body.steps_per_half
    )


@router.get("/{match_id}", response_model=MatchState, operation_id="getMatch")
def get_match(match_id: str, engine: Worker):
    return require_match(engine, match_id)


@router.get("/{match_id}/frames", response_model=FramesPage, operation_id="getFrames")
def get_frames(
    match_id: str,
    engine: Worker,
    from_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    state = require_match(engine, match_id)
    frames = engine.store.repo.get_frames(match_id, from_seq=from_seq, limit=limit)
    next_seq = frames[-1].seq + 1 if frames else from_seq
    latest = engine.db.match_frames.find_one({"match_id": match_id}, sort=[("seq", -1)])
    finished = state.phase == "full_time" and (latest is None or next_seq > latest["seq"])
    return FramesPage(
        match_id=match_id, frames=frames, next_seq=None if finished else next_seq, phase=state.phase
    )


@router.get("/{match_id}/events", response_model=list[MatchEvent], operation_id="getEvents")
def get_events(match_id: str, engine: Worker, after_event_id: str | None = None):
    require_match(engine, match_id)
    try:
        return engine.store.repo.get_events(match_id, after_event_id=after_event_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get(
    "/{match_id}/decisions", response_model=list[CoachDecision], operation_id="getDecisions"
)
def get_decisions(match_id: str, engine: Worker):
    require_match(engine, match_id)
    return list(engine.store.read(match_id)["_engine"]["decisions"].values())


@router.get("/{match_id}/actions", response_model=list[Action], operation_id="getActions")
def get_actions(match_id: str, engine: Worker):
    require_match(engine, match_id)
    return list(engine.store.read(match_id)["_engine"]["actions"].values())


@router.get("/{match_id}/recovery", operation_id="getRecovery")
def get_recovery(match_id: str, engine: Worker) -> dict[str, int | bool]:
    require_match(engine, match_id)
    data = engine.store.read(match_id)["_engine"]
    return {"recoveries": data["recoveries"], "crash_fired": data["crash_fired"]}


@router.get("/{match_id}/briefings/{team_id}", response_model=Briefing, operation_id="getBriefing")
def get_briefing(
    match_id: str,
    team_id: TeamId,
    briefings: Annotated[BriefingService, Depends(get_briefing_service)],
):
    try:
        return briefings.get_briefing(match_id, team_id)
    except BriefingNotFoundError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/{match_id}/reset", response_model=MatchState, operation_id="resetMatch")
def reset_match(match_id: str, engine: Worker):
    state = require_match(engine, match_id)
    return engine.create(
        state.seed, state.steps_per_half
    )  # New run ID preserves the old audit trail.
