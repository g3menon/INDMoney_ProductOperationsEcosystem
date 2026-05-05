"""Structured logging with correlation IDs (O1)."""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.context import correlation_id as _cid_var
from app.core.config import get_settings


class CorrelationFilter(logging.Filter):
    """Injects correlation_id from logging extra into the formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = _cid_var.get()  # type: ignore[attr-defined]
        return True


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] [cid=%(correlation_id)s] %(message)s",
        ),
    )
    handler.addFilter(CorrelationFilter())
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
