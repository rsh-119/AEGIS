"""
Structured logging for Aegis.

In production  (APP_ENV=production): JSON lines to stdout for Loki/ELK/Datadog.
In development (APP_ENV=development): colour-coded human-readable output.

Request ID propagation via ContextVar — set once per request by
RequestIDMiddleware and automatically included in every log line.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

# Set by RequestIDMiddleware for every inbound request
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    """One compact JSON object per log line."""

    # fields the LogRecord always carries that we don't want to double-emit
    _SKIP = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":      record.levelname,
            "logger":     record.name,
            "request_id": request_id_var.get("-"),
            "msg":        record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        # include any extra= fields attached by the caller
        for k, v in record.__dict__.items():
            if k not in self._SKIP:
                obj[k] = v
        return json.dumps(obj, default=str)


class _PrettyFormatter(logging.Formatter):
    """Dev-mode: colour-coded with request_id prefix."""

    _COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35;1m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        rid   = request_id_var.get("-")[:8]
        ts    = time.strftime("%H:%M:%S", time.gmtime(record.created))
        msg   = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return (
            f"{color}[{ts}] [{record.levelname:<8}] [{rid}] "
            f"{record.name}: {msg}{self._RESET}"
        )


def configure_logging(app_env: str = "development", log_level: str = "INFO") -> None:
    """
    Call once at application startup (before any logger is used).

    app_env="production"  → JSON lines to stdout
    app_env="development" → coloured human-readable output
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JsonFormatter() if app_env == "production" else _PrettyFormatter()
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # silence noisy libraries
    for noisy in ("urllib3", "httpx", "asyncio", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
