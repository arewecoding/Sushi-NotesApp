"""
Sushi Feature Flags
====================
Runtime feature flags loaded from ~/.sushi/flags.json.
Call load_flags() at app startup after configure_logging().
"""

import json
from pathlib import Path
from typing import Any
import structlog

log = structlog.get_logger(__name__)

FLAGS_PATH = Path.home() / ".sushi" / "flags.json"
_flags: dict[str, Any] = {}

DEFAULT_FLAGS = {
    "select_tool_enabled": True,
    "text_tool_enabled": False,
    "image_import_enabled": False,
    "jbook_enabled": False,
    "shape_recognition_enabled": False,
    "pdf_annotation_enabled": False,
    "ml_calibration_enabled": False,
}


def load_flags() -> None:
    """Load feature flags from disk. Falls back to empty dict on error."""
    global _flags
    if FLAGS_PATH.exists():
        try:
            _flags = json.loads(FLAGS_PATH.read_text(encoding="utf-8"))
            log.info("flags_loaded", flags=_flags)
        except Exception as e:
            log.warning("flags_load_failed", error=str(e))
            _flags = {}
    else:
        _flags = {}


def write_default_flags() -> None:
    """Write the default flags file if it does not already exist."""
    if FLAGS_PATH.exists():
        return

    from sushi.filesys import atomic_write

    FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(FLAGS_PATH, json.dumps(DEFAULT_FLAGS, indent=2))
    log.info("default_flags_written", path=str(FLAGS_PATH))


def flag(name: str, default: bool = False) -> bool:
    """Check whether a feature flag is enabled."""
    return bool(_flags.get(name, default))
