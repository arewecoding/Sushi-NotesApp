"""
Sushi Data Migrations
======================
Version migration framework for canvas and book data formats.
Register migrations with @register_canvas_migration / @register_book_migration.
"""

from typing import Callable
import structlog

log = structlog.get_logger(__name__)

CANVAS_MIGRATIONS: dict[str, Callable[[dict], dict]] = {}
BOOK_MIGRATIONS: dict[str, Callable[[dict], dict]] = {}

CURRENT_CANVAS_VERSION = "1.0"
CURRENT_BOOK_VERSION = "1.0"


def register_canvas_migration(from_version: str):
    """Decorator to register a canvas migration from a specific version."""
    def decorator(fn: Callable[[dict], dict]):
        CANVAS_MIGRATIONS[from_version] = fn
        return fn
    return decorator


def register_book_migration(from_version: str):
    """Decorator to register a book migration from a specific version."""
    def decorator(fn: Callable[[dict], dict]):
        BOOK_MIGRATIONS[from_version] = fn
        return fn
    return decorator


def migrate_canvas(data: dict) -> dict:
    """Run canvas data through the migration chain until current version."""
    version = data.get("metadata", {}).get("version", "1.0")
    while version in CANVAS_MIGRATIONS:
        log.info("migrating_canvas", from_version=version)
        data = CANVAS_MIGRATIONS[version](data)
        version = data["metadata"]["version"]
    return data


def migrate_book(data: dict) -> dict:
    """Run book data through the migration chain until current version."""
    version = data.get("metadata", {}).get("version", "1.0")
    while version in BOOK_MIGRATIONS:
        log.info("migrating_book", from_version=version)
        data = BOOK_MIGRATIONS[version](data)
        version = data["metadata"]["version"]
    return data
