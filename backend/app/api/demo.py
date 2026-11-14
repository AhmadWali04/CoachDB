from fastapi import APIRouter

from app.schemas import InjectCrashRequest, InjectCrashResponse

from .stubs import NOT_IMPLEMENTED, not_implemented

router = APIRouter(prefix="/demo", tags=["demo"], responses=NOT_IMPLEMENTED)


@router.post("/inject-crash", response_model=InjectCrashResponse, operation_id="injectCrash")
def inject_crash(body: InjectCrashRequest) -> InjectCrashResponse:
    raise not_implemented("A")
