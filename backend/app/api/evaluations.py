from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.evaluation import EvaluationRunner
from app.orchestration.dependencies import get_match_service
from app.schemas import ErrorResponse
from app.schemas.evaluation import EvaluationBatch, RunEvaluationRequest

router = APIRouter(
    prefix="/evaluations",
    tags=["evaluations"],
    responses={404: {"model": ErrorResponse, "description": "Unknown batch"}},
)


@lru_cache
def get_evaluation_runner() -> EvaluationRunner:
    return EvaluationRunner(get_match_service())


Runner = Annotated[EvaluationRunner, Depends(get_evaluation_runner)]


@router.post("", response_model=EvaluationBatch, status_code=202, operation_id="runEvaluation")
def run_evaluation(body: RunEvaluationRequest, runner: Runner) -> EvaluationBatch:
    """Start a seeded, side-swapped batch (2 matches per seed). Poll GET for progress.
    With AI coaches enabled, every halftime calls the model."""
    return runner.get(runner.start(body.seeds, body.steps_per_half))


@router.get("/{batch_id}", response_model=EvaluationBatch, operation_id="getEvaluation")
def get_evaluation(batch_id: str, runner: Runner) -> EvaluationBatch:
    batch = runner.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"unknown evaluation batch {batch_id}")
    return batch
