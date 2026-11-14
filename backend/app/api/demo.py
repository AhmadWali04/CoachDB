from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.orchestration import MatchService, UnknownMatch
from app.orchestration.dependencies import get_match_service
from app.schemas import InjectCrashRequest, InjectCrashResponse

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/inject-crash", response_model=InjectCrashResponse, operation_id="injectCrash")
def inject_crash(
    body: InjectCrashRequest, service: Annotated[MatchService, Depends(get_match_service)]
) -> InjectCrashResponse:
    """Arm a one-time crash in this match's halftime worker, after a plan is
    applied by the simulator and before the ledger records it (PRD §9.3)."""
    try:
        armed = service.arm_crash(body.match_id)
    except UnknownMatch as exc:
        raise HTTPException(status_code=404, detail=f"unknown match {body.match_id}") from exc
    return InjectCrashResponse(match_id=body.match_id, point=body.point, armed=armed)
