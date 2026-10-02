"""Structured JSON logging for the whole application (NFR-003)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_STANDARD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render one LogRecord as a single-line JSON object.

    Keys: ``timestamp`` (ISO 8601 UTC), ``level``, ``logger``, ``message``;
    ``exc`` carries the formatted traceback when the record has one; extra
    attributes (``logger.info("...", extra={...})``) are added as further keys,
    skipping names starting with ``_`` and the standard LogRecord fields.

    Example:
        fmt = JsonFormatter()
        record = logging.LogRecord("app", 20, __file__, 7, "hi", (), None)
        fmt.format(record)
        # '{"level": "INFO", "logger": "app", "message": "hi", "timestamp": ...}'
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {}
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD_ATTRS:
                continue
            payload[key] = value
        payload["timestamp"] = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        payload["level"] = record.levelname
        payload["logger"] = record.name
        payload["message"] = record.getMessage()
        if record.exc_info is not None:
            exc_info = record.exc_info
            if not isinstance(exc_info, tuple):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
            payload["exc"] = self.formatException(exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def setup_logging(level: str) -> None:
    """Configure JSON logging on the root logger (idempotent handler, live level).

    Attaches a single StreamHandler with :class:`JsonFormatter` (once per
    process) and (re)applies the root level from ``level`` on every call, so
    late config changes (e.g. test-injected Settings) take effect.

    Example:
        setup_logging(get_settings().log_level)
        logging.getLogger("petrinet.api").info("app started")
    """
    global _configured
    root = logging.getLogger()
    root.setLevel(level.upper())
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    _configured = True
