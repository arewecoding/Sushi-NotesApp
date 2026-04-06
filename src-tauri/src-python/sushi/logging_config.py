"""
Sushi Structured Logging Configuration
========================================
Configures structlog with JSON rendering and rotating file output.
Call configure_logging() at app startup before any other imports.
"""

import structlog
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path.home() / ".sushi" / "logs"


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog with JSON rendering and rotating file handler."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = RotatingFileHandler(
        LOG_DIR / "sushi.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    handler.setLevel(getattr(logging, level))
    logging.basicConfig(handlers=[handler], level=getattr(logging, level))
