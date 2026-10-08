"""FastAPI application entrypoint.

Application factory: registers the API routes (per ``docs/ARCHITECTURE.md``),
the five typed error handlers (per ``docs/ADR/0006-error-handling.md``), the
liveness probe, and the static frontend. Example:

    uvicorn petrinet.api.app:app --port 8000
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from petrinet.api.routes import router
from petrinet.config import Settings, get_settings
from petrinet.errors import (
    CapExceededError,
    ConflictError,
    ParseError,
    SolverError,
    TransitionNotEnabledError,
    UnknownSessionError,
    UnknownTaskError,
    UnsupportedModelError,
    ValidationError,
)
from petrinet.logging_setup import setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application with routes and error handlers registered.

    ``settings`` defaults to :func:`get_settings()`; tests may inject a
    ``Settings`` with a temporary ``DB_PATH``. Example:

        >>> app = create_app()
        >>> app.title
        'Petri Net Web'
    """
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="Petri Net Web", version="0.1.0")

    @app.middleware("http")
    async def _request_timing(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Record the request start time so error handlers can log duration_ms."""
        request.state.started_at = time.perf_counter()
        return await call_next(request)

    def _duration_ms(request: Request) -> int:
        """Milliseconds elapsed since the request started (0 if unknown)."""
        started = getattr(request.state, "started_at", None)
        if started is None:
            return 0
        return int((time.perf_counter() - started) * 1000)

    @app.exception_handler(ParseError)
    async def _handle_parse_error(request: Request, exc: ParseError) -> JSONResponse:
        """Map ParseError to the 422 ``parse_failed`` body (ADR-0006)."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "parse_failed",
                "session_id": getattr(exc, "session_id", None),
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "parse_failed",
                    "message": str(exc),
                    "details": {"position": exc.position},
                }
            },
        )

    @app.exception_handler(ValidationError)
    async def _handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
        """Map ValidationError to the 422 ``validation_failed`` body (ADR-0006)."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "validation_failed",
                "session_id": getattr(exc, "session_id", None),
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": str(exc),
                    "details": exc.problems,
                }
            },
        )

    @app.exception_handler(UnknownSessionError)
    async def _handle_unknown_session(request: Request, exc: UnknownSessionError) -> JSONResponse:
        """Map UnknownSessionError to the 404 ``unknown_session`` body (ADR-0006)."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "unknown_session",
                "session_id": getattr(exc, "session_id", None),
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "unknown_session",
                    "message": str(exc),
                    "details": {"session_id": exc.session_id},
                }
            },
        )

    @app.exception_handler(CapExceededError)
    async def _handle_cap_exceeded(request: Request, exc: CapExceededError) -> JSONResponse:
        """Map CapExceededError to the 413 ``cap_exceeded`` body (ADR-0006)."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "cap_exceeded",
                "session_id": getattr(exc, "session_id", None),
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "cap_exceeded",
                    "message": str(exc),
                    "details": {"limit": exc.limit, "suggestion": "coverability"},
                }
            },
        )

    @app.exception_handler(TransitionNotEnabledError)
    async def _handle_transition_not_enabled(
        request: Request, exc: TransitionNotEnabledError
    ) -> JSONResponse:
        """Map TransitionNotEnabledError to the 409 ``transition_not_enabled`` body."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "transition_not_enabled",
                "session_id": getattr(exc, "session_id", None),
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "transition_not_enabled",
                    "message": str(exc),
                    "details": {"transition": exc.transition, "marking": list(exc.marking)},
                }
            },
        )

    @app.exception_handler(UnknownTaskError)
    async def _handle_unknown_task(request: Request, exc: UnknownTaskError) -> JSONResponse:
        """Map UnknownTaskError to the 422 ``unknown_task`` body (section 2.6)."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "unknown_task",
                "session_id": None,
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "unknown_task",
                    "message": str(exc),
                    "details": {"task_id": exc.task_id},
                }
            },
        )

    @app.exception_handler(UnsupportedModelError)
    async def _handle_unsupported_model(
        request: Request, exc: UnsupportedModelError
    ) -> JSONResponse:
        """Map UnsupportedModelError to the 422 ``unsupported_model`` body."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "unsupported_model",
                "session_id": None,
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "unsupported_model",
                    "message": str(exc),
                    "details": {"feature": exc.feature},
                }
            },
        )

    @app.exception_handler(ConflictError)
    async def _handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
        """Map ConflictError to the 409 ``conflict`` body."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "conflict",
                "session_id": None,
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "conflict",
                    "message": str(exc),
                    "details": {
                        "transitions": list(exc.transitions),
                        "place": exc.place,
                    },
                }
            },
        )

    @app.exception_handler(SolverError)
    async def _handle_solver_error(request: Request, exc: SolverError) -> JSONResponse:
        """Map SolverError to the 500 ``solver_failed`` body."""
        logging.getLogger("petrinet.api").error(
            "error",
            extra={
                "error_code": "solver_failed",
                "session_id": None,
                "duration_ms": _duration_ms(request),
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "solver_failed",
                    "message": str(exc),
                    "details": {},
                }
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe.

        Example:
            >>> healthz()
            {'status': 'ok'}
        """
        return {"status": "ok"}

    app.include_router(router)

    static_dir = Path(settings.petrinet_static_dir)
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


app = create_app()
