"""Centralized logging utilities for the Document Intelligence Refinery.

This module exposes a `get_logger` helper that returns a configured logger
instance with a consistent, structured log format across the project.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        base: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in base:
                continue
            # Avoid serializing non-JSON-serializable objects directly
            try:
                json.dumps(value)
                base[key] = value
            except TypeError:
                base[key] = repr(value)
        return json.dumps(base, ensure_ascii=False)


_LOG_LEVEL = os.getenv("REFINERY_LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = os.getenv("REFINERY_LOG_FORMAT", "json")  # "json" or "plain"


def _configure_root_logger() -> None:
    """Configure the root logger exactly once."""

    if getattr(_configure_root_logger, "_configured", False):
        return

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    # Remove any pre-existing handlers to avoid duplicate logs in some environments.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    if _LOG_FORMAT == "plain":
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    handler.setFormatter(formatter)
    root.addHandler(handler)

    setattr(_configure_root_logger, "_configured", True)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger with centralized configuration applied."""

    _configure_root_logger()
    return logging.getLogger(name)

