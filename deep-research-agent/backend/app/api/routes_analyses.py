from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_analysis_service, get_job_store
from app.models.schemas import (
    AnalysisCreateRequest,
    AnalysisJobCreateResponse,
    AnalysisJobResponse,
    JobStatus,
)
from app.services.analysis_service import AnalysisService
from app.services.job_store import JobStore

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=AnalysisJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    payload: AnalysisCreateRequest,
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisJobCreateResponse:
    """
    Kick off a multi-agent competitive intelligence run in the background and
    return a job id immediately (HTTP 202: request accepted, not yet complete).
    """
    job_id = await analysis_service.start_job(
        payload.target_company, payload.competitors, payload.focus_areas
    )
    return AnalysisJobCreateResponse(job_id=job_id, status=JobStatus.pending)


@router.get("/{job_id}", response_model=AnalysisJobResponse)
async def get_analysis(
    job_id: str, job_store: JobStore = Depends(get_job_store)
) -> AnalysisJobResponse:
    """Poll for job status + live agent trace. Raises 404 via JobNotFoundError."""
    return await job_store.get(job_id)


@router.get("", response_model=list[AnalysisJobResponse])
async def list_analyses(
    limit: int = 20, job_store: JobStore = Depends(get_job_store)
) -> list[AnalysisJobResponse]:
    return await job_store.list_recent(limit=limit)
