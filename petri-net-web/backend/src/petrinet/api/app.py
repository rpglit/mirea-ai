"""FastAPI application entrypoint.

Serves the JSON API (routes are registered per ``docs/ARCHITECTURE.md``) and the
static frontend. Example:

    uvicorn petrinet.api.app:app --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(os.environ.get("PETRINET_STATIC_DIR", "/app/static"))


def create_app() -> FastAPI:
    """Build the FastAPI application.

    Example:
        >>> app = create_app()
        >>> app.title
        'Petri Net Web'
    """
    app = FastAPI(title="Petri Net Web", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe.

        Example:
            >>> healthz()
            {'status': 'ok'}
        """
        return {"status": "ok"}

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

    return app


app = create_app()
