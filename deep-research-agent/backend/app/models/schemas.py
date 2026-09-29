"""
API-facing Pydantic models (the HTTP contract).

Kept separate from the LangGraph state (`app/agents/state.py`) on purpose:
the wire format and the internal graph state evolve independently. Coupling
them means every internal refactor becomes a breaking API change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    title: str
    url: str


class AnalysisCreateRequest(BaseModel):
    target_company: str = Field(min_length=2, max_length=200, examples=["Anthropic"])
    competitors: list[str] | None = Field(default=None, max_length=10)
    focus_areas: list[str] | None = Field(default=None, max_length=10)


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TraceEvent(BaseModel):
    node: str
    status: JobStatus
    detail: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    target_company: str
    competitors: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    trace: list[TraceEvent] = Field(default_factory=list)
    research_plan: dict[str, list[str]] = Field(default_factory=dict)
    key_facts: dict[str, str] = Field(default_factory=dict)
    report_markdown: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    revision_count: int = 0
    error: str | None = None


class AnalysisJobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class HealthResponse(BaseModel):
    status: str
    app_env: str
    claude_model: str
