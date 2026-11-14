from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.orchestration.dependencies import get_engine
from app.orchestration.engine import Engine
from app.schemas import InjectCrashRequest, InjectCrashResponse

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/inject-crash", response_model=InjectCrashResponse, operation_id="injectCrash")
def inject_crash(body: InjectCrashRequest, engine: Annotated[Engine, Depends(get_engine)]):
    if engine.store.read(body.match_id) is None:
        raise HTTPException(404, "Match not found")
    if not engine.store.arm_crash(body.match_id):
        raise HTTPException(409, "Arm the crash during the first half, before halftime execution")
    return InjectCrashResponse(match_id=body.match_id, point=body.point, armed=True)
