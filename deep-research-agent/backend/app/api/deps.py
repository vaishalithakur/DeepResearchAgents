"""
FastAPI dependency providers.

Shared, expensive-to-construct objects (the Anthropic client, the compiled
LangGraph, the job store) are built once in `main.py`'s lifespan and stashed
on `app.state`. These `Depends(...)` functions just fetch them back out,
request by request. This is the standard FastAPI pattern for singletons
that beats module-level globals: it's explicit, and tests can swap any of
them via `app.dependency_overrides[get_claude_client] = lambda: fake_client`
without monkeypatching imports.
"""

from __future__ import annotations

from fastapi import Request

from app.agents.claude_client import ClaudeClient
from app.config import Settings
from app.services.analysis_service import AnalysisService
from app.services.job_store import JobStore


def get_app_settings(request: Request) -> Settings:
    """
    Return the Settings instance this app was actually started with.

    Deliberately reads `request.app.state.settings` (set once in the
    lifespan) rather than calling `get_settings()` directly: the latter is a
    process-wide `lru_cache`d singleton and would silently ignore a
    `Settings` instance a test passed into `create_app(settings=...)`.
    """
    return request.app.state.settings


def get_claude_client(request: Request) -> ClaudeClient:
    return request.app.state.claude_client


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service
