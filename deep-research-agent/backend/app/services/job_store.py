"""
In-memory async job store.

A single `asyncio.Lock` guards the dict because job creation/updates can
race between the HTTP request handler and the background task driving the
graph. This is intentionally simple and process-local: fine for a single
uvicorn worker demo. The `JobStore` interface is narrow enough that
swapping in Redis or Postgres for a multi-worker production deployment
means writing one new class, not touching any call sites -- see the
"Scaling this to production" section of the README.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.exceptions import JobNotFoundError
from app.models.schemas import AnalysisJobResponse, JobStatus, TraceEvent


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJobResponse] = {}
        # Wall-clock timestamps alone aren't a safe sort key: on fast
        # hardware, jobs created back-to-back can land in the same
        # microsecond. A monotonically increasing counter gives `list_recent`
        # a tie-proof ordering.
        self._insertion_order: dict[str, int] = {}
        self._next_seq = 0
        self._lock = asyncio.Lock()

    async def create(
        self, job_id: str, target_company: str, competitors: list[str] | None = None
    ) -> AnalysisJobResponse:
        now = datetime.now(UTC)
        job = AnalysisJobResponse(
            job_id=job_id,
            status=JobStatus.pending,
            target_company=target_company,
            competitors=competitors or [],
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._jobs[job_id] = job
            self._insertion_order[job_id] = self._next_seq
            self._next_seq += 1
        return job

    async def get(self, job_id: str) -> AnalysisJobResponse:
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"No analysis job with id '{job_id}'")
        return job

    async def append_trace(
        self, job_id: str, node: str, status: JobStatus, detail: str = ""
    ) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.trace.append(TraceEvent(node=node, status=status, detail=detail))
            job.updated_at = datetime.now(UTC)

    async def update(self, job_id: str, **fields: object) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(UTC)

    async def list_recent(self, limit: int = 20) -> list[AnalysisJobResponse]:
        async with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: self._insertion_order[j.job_id],
                reverse=True,
            )
        return jobs[:limit]
