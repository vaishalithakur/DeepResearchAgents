"""
Domain exceptions + centralized FastAPI exception handlers.

Design principle: route/service code raises *semantic* exceptions
(`JobNotFoundError`, `UpstreamModelError`, ...) instead of calling
`raise HTTPException(...)` inline everywhere. The handlers registered in
`main.py` translate those into consistent JSON error envelopes and the
right HTTP status codes. This keeps business logic testable without
importing FastAPI/Starlette, and guarantees every error the client sees
has the same shape.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.logging_config import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all application (non-framework) errors."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class JobNotFoundError(AppError):
    status_code = 404
    error_code = "job_not_found"


class InvalidRequestError(AppError):
    status_code = 422
    error_code = "invalid_request"


class UpstreamModelError(AppError):
    """Raised when the Anthropic API call fails after retries."""

    status_code = 502
    error_code = "upstream_model_error"


class RateLimitExceededError(AppError):
    status_code = 429
    error_code = "rate_limit_exceeded"


def _error_body(exc: AppError) -> dict:
    return {
        "error": {
            "code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error",
        path=request.url.path,
        error_code=exc.error_code,
        message=exc.message,
    )
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {},
            }
        },
    )
