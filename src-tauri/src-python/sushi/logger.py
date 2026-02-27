"""
Sushi Logger
=============
Centralized logging with source-tagged formatting.
"""

from enum import Enum
import logging
import sys
import os
from pathlib import Path


class LogSource(Enum):
    """Namespace: WHERE is the log coming from?"""

    SYSTEM = "SYSTEM"
    DB = "DATABASE"
    RAG = "RAG_ENGINE"
    API = "API_LAYER"


class LogLevel(Enum):
    """Level: HOW urgent is it?"""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class _DefaultLogSourceFilter(logging.Filter):
    """
    Inject a default ``log_source`` attribute into any LogRecord that
    doesn't already have one.

    This is needed because the RAG sub-modules use standard
    ``logging.getLogger(__name__)`` without setting ``log_source``,
    but the Sushi formatter expects it.  Without this filter, every
    RAG log call causes ``KeyError: 'log_source'`` inside the formatter.
    """

    def __init__(self, default: str = "RAG_ENGINE"):
        super().__init__()
        self._default = default

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "log_source"):
            record.log_source = self._default
        return True  # always emit


class SushiLogger:
    """Singleton logger with source-tagged formatting."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.logger = logging.getLogger("sushi")
        self.logger.setLevel(logging.DEBUG)

        # Avoid duplicate handlers on re-import
        if self.logger.handlers:
            return

        formatter = logging.Formatter(
            "%(asctime)s | [%(log_source)s] | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _filter = _DefaultLogSourceFilter()

        # Console output
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console.addFilter(_filter)
        self.logger.addHandler(console)

        # File output (~/.sushi/sushi.log)
        log_dir = Path.home() / ".sushi"
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_dir / "sushi.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_filter)
            self.logger.addHandler(file_handler)
        except Exception:
            sys.stderr.write(f"Failed to create log file at {log_dir}\n")

        # ── Also configure child loggers for the RAG package ──────────────
        # By default, RAG module loggers propagate to the root logger, which
        # may have its own handler that ALSO lacks the filter.  Redirect them
        # explicitly to the sushi logger so they always go through our filter.
        rag_logger = logging.getLogger("sushi.rag")
        rag_logger.setLevel(logging.DEBUG)
        rag_logger.propagate = True  # goes up to "sushi" logger above

    def log(self, source: LogSource, level: LogLevel, message: str, meta: dict = None):
        """The main entry point for logging."""
        extra = {"log_source": source.value}
        full_message = f"{message} | Meta: {meta}" if meta else message
        self.logger.log(level.value, full_message, extra=extra)


# Global instance
sys_log = SushiLogger()
