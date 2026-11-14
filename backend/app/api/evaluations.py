from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.orchestration.dependencies import get_engine
from app.orchestration.engine import Engine
from app.schemas.evaluation import BatchRequest, EvaluationBatch

router = APIRouter(prefix="/evaluations", tags=["evaluation"])


@router.post("", response_model=EvaluationBatch, status_code=202, operation_id="runBatch")
def run_batch(body: BatchRequest, engine: Annotated[Engine, Depends(get_engine)]):
    return engine.batch(body)


@router.get("/{batch_id}", response_model=EvaluationBatch, operation_id="getEvaluation")
def get_evaluation(batch_id: str, engine: Annotated[Engine, Depends(get_engine)]):
    doc = engine.db.evaluations.find_one({"batch_id": batch_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(404, "Evaluation not found")
    return doc
