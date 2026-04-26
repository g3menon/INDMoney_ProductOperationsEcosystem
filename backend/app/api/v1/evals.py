"""Automated eval runner (Phase 1: infrastructure / contract checks)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.evals.phase1_checks import Phase1EvalReport, run_phase1_evals
from app.schemas.common import APIEnvelope

router = APIRouter(prefix="/evals")


class EvalRunRequest(BaseModel):
    suite: Literal["phase1"] = Field(default="phase1", description="Eval suite to run.")


@router.post("/run", response_model=APIEnvelope[dict[str, Any]])
async def run_evals(body: EvalRunRequest | None = None) -> APIEnvelope[dict[str, Any]]:
    body = body or EvalRunRequest()
    if body.suite != "phase1":
        return APIEnvelope(
            success=False,
            message="unsupported_suite",
            data={"supported": ["phase1"]},
            errors=[],
        )
    report: Phase1EvalReport = run_phase1_evals()
    passed = report.score >= 85.0
    return APIEnvelope(
        success=passed,
        message="eval_complete" if passed else "eval_below_threshold",
        data=report.model_dump(),
    )
