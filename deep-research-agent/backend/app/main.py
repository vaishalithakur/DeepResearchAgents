"""
Application entrypoint / factory.

`create_app()` builds a fresh FastAPI instance so tests can construct
isolated apps (e.g. with overridden settings) instead of importing one
shared module-level singleton. The module-level `app` at the bottom is
what `uvicorn app.main:app` actually serves.

Startup work (constructing the Anthropic client, compiling the LangGraph
graph) happens once in the `lifespan` context manager -- not per-request,
and not at import time (which would break `pytest --collect-only` and any
tooling that imports the module without real credentials).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agents.claude_client import ClaudeClient
from app.agents.graph import build_analysis_graph
from app.api.routes_analyses import router as analyses_router
from app.api.routes_health import router as health_router
from app.config import Settings, get_settings
from app.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from app.services.analysis_service import AnalysisService
from app.services.job_store import JobStore

logger = get_logger(__name__)


def _bridge_langsmith_env(settings: Settings) -> None:
    """
    LangSmith's tracer and LangGraph's own tracing hooks read process env
    vars directly -- they have no API surface we can hand `settings` to.
    `pydantic-settings` only populates the `Settings` object, not
    `os.environ`, so we bridge the handful of relevant vars here, once,
    before the graph is built (tracing hooks are established at
    graph-build/first-run time, so this must run first). `Settings` is the
    single source of truth: it wins over any stray var already in the shell.
    """
    if not settings.langsmith_enabled:
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key or ""
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint


def _build_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """
    Return a lifespan context manager closed over the exact `Settings`
    instance `create_app()` resolved -- not a fresh call to the process-wide
    `get_settings()` singleton, which would silently ignore a `Settings`
    object a caller (or a test) passed into `create_app(settings=...)`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings)
        logger.info("app_starting", app_env=settings.app_env, claude_model=settings.claude_model)

        _bridge_langsmith_env(settings)

        claude_client = ClaudeClient(settings)
        job_store = JobStore()
        graph = build_analysis_graph(claude_client, settings)
        analysis_service = AnalysisService(graph, job_store, settings)

        app.state.settings = settings
        app.state.claude_client = claude_client
        app.state.job_store = job_store
        app.state.analysis_service = analysis_service

        yield

        logger.info("app_shutting_down")
        await analysis_service.shutdown()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Fieldnote Intelligence",
        description="LangGraph + Claude multi-agent competitive intelligence service",
        version="0.1.0",
        lifespan=_build_lifespan(settings),
    )

    # --- rate limiting -----------------------------------------------------
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    )
    app.state.limiter = limiter
    # Starlette's `add_exception_handler` type hint expects a handler typed
    # against the base `Exception`, but ours are correctly narrowed to the
    # specific exception they handle (a stricter, more useful signature at
    # every call site). This is a known imprecision in Starlette's stubs,
    # not a real type-safety issue -- the runtime dispatches by the
    # registered exception *type*, not the handler's declared parameter type.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # --- middleware (order matters: outermost added last) ------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    # --- exception handlers -------------------------------------------------
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # --- routes --------------------------------------------------------------
    app.include_router(health_router)
    app.include_router(analyses_router)

    return app


app = create_app()
