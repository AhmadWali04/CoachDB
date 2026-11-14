from fastapi import HTTPException, status

from app.schemas import ErrorResponse

NOT_IMPLEMENTED = {501: {"model": ErrorResponse, "description": "Not implemented yet"}}


def not_implemented(owner: str) -> HTTPException:
    """Phase 0 placeholder. Replace with the real handler; keep the response_model."""
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented yet (owner: {owner}). See CHECKLIST.md.",
    )
