"""
Cross-cutting HTTP middleware.

RequestContextMiddleware:
    - Generates/propagates an `X-Request-ID` header.
    - Binds it (plus method/path) into structlog's contextvars so every
      log line emitted while handling this request carries it automatically.
    - Measures wall-clock latency and emits one structured access log line
      per request (the "what actually happened" audit trail).

Two middlewares in one file on purpose: they're small, always used
together, and colocating them avoids import spaghetti in `main.py`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import get_logger

logger = get_logger("access")

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=request.method, path=request.url.path
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - re-raised after logging, handled globally
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("request_failed", duration_ms=duration_ms)
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
