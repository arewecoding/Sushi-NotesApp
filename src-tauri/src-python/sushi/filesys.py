"""
Sushi File System Operations
==============================
File I/O helpers, filename utilities, and CRUD operations for notes and directories.
"""

import json
import re
import shutil
import time
from typing import Optional
from pathlib import Path

from sushi.cache_db import FileIndex
from sushi.note_schema import JNote
from sushi.logger import sys_log, LogSource, LogLevel


# ==========================================
# File I/O Helpers
# ==========================================


def load_jnote(file_path: Path) -> Optional[JNote]:
    """Reads a full JNote object from a .jnote file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JNote.from_dict(data, filepath=str(file_path))
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.ERROR,
            f"Failed to load JNote from {file_path}: {e}",
        )
        return None


def save_jnote(file_path: Path, note: JNote) -> None:
    """Writes a JNote object to disk without updating timestamps."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(note.to_dict(), f, indent=2)
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.ERROR,
            f"Failed to save JNote to {file_path}: {e}",
        )


# ==========================================
# Filename Utilities
# ==========================================

SHORT_ID_LEN = 7
MAX_SLUG_LEN = 50


def slugify(text: str, max_len: int = MAX_SLUG_LEN) -> str:
    """
    Convert text to a filesystem-safe slug.
    Lowercase, spaces → hyphens, strip illegal/special chars, truncate.
    """
    slug = text.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")

    if len(slug) > max_len:
        slug = slug[:max_len]
        last_hyphen = slug.rfind("-")
        if last_hyphen > max_len // 2:
            slug = slug[:last_hyphen]

    return slug or "untitled"


def generate_filename(title: str, note_id: str) -> str:
    """
    Generate a human-readable filename: {slug}-{short_id}.jnote
    Example: 'my-cool-note-4f1139b.jnote'
    """
    slug = slugify(title)
    short_id = note_id[:SHORT_ID_LEN]
    return f"{slug}-{short_id}.jnote"


def extract_short_id(filename: str) -> Optional[str]:
    """
    Parse the short ID (last 7 chars before .jnote) from a filename.
    'my-cool-note-4f1139b.jnote' → '4f1139b'
    """
    stem = Path(filename).stem
    if len(stem) < SHORT_ID_LEN:
        return None
    short_id = stem[-SHORT_ID_LEN:]
    if re.match(r"^[a-f0-9]+$", short_id):
        return short_id
    return None


def get_note_filepath(db: FileIndex, note_id: str) -> Optional[Path]:
    """
    Derive the full file path for a note from its DB metadata.
    Uses generate_filename() based on the DB title. If the expected file
    doesn't exist, falls back to a glob search by short ID.
    """
    meta = db.get_metadata(note_id)
    if not meta:
        return None
    filename = generate_filename(meta.note_title, meta.note_id)
    expected_path = meta.note_dir / filename

    if expected_path.exists():
        return expected_path

    # Fallback: file may have a stale name — search by short ID
    short_id = meta.note_id[:SHORT_ID_LEN]
    for f in meta.note_dir.glob(f"*-{short_id}.jnote"):
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"Filepath fallback: expected {filename}, found {f.name}",
        )
        return f

    return expected_path


# ==========================================
# Note CRUD Operations
# ==========================================


def create_new_note(base_dir: str, title: str = "Untitled Note") -> Optional[JNote]:
    """
    Creates a new JNote and saves it to disk.
    Uses human-readable filename: {slug}-{short_id}.jnote
    Watcher will handle the DB update.
    """
    try:
        note = JNote.create_new(title)
        note_id = note.metadata.note_id
        filename = generate_filename(title, note_id)
        file_path = Path(base_dir) / filename

        note.metadata.last_known_path = str(file_path.resolve())

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(note.to_dict(), f, indent=2)

        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"Created note on disk: {file_path}"
        )
        return note
    except Exception as e:
        sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Failed to create note: {e}")
        return None


def update_note(db: FileIndex, note: JNote) -> Optional[float]:
    """
    Updates a note on disk and returns the new mtime.
    Performs drift detection: if title changed, renames the file.
    RETURNS timestamp for Echo Suppression.
    """
    try:
        meta = db.get_metadata(note.metadata.note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Note not found in DB: {note.metadata.note_id}",
            )
            return None

        actual_path = get_note_filepath(db, meta.note_id)
        if not actual_path or not actual_path.exists():
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Note file not found on disk for: {meta.note_id}",
            )
            return None

        # Derive expected filename from the NEW title
        expected_filename = generate_filename(note.metadata.title, meta.note_id)
        expected_path = meta.note_dir / expected_filename

        note.metadata.update_timestamp()

        # Drift detection: actual filename != expected → save then rename
        if actual_path.name != expected_filename:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"Title drift: renaming {actual_path.name} -> {expected_filename}",
            )

            # Save content with last_known_path pointing to CURRENT path
            note.metadata.last_known_path = str(actual_path.resolve())
            with open(actual_path, "w", encoding="utf-8") as f:
                json.dump(note.to_dict(), f, indent=2)

            # Rename with retry (watchdog may briefly hold the file)
            renamed = False
            for attempt in range(5):
                try:
                    actual_path.rename(expected_path)
                    renamed = True
                    break
                except OSError:
                    if attempt < 4:
                        time.sleep(0.2)

            if renamed:
                note.metadata.last_known_path = str(expected_path.resolve())
                save_jnote(expected_path, note)
                file_path = expected_path
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Rename succeeded: {expected_filename}",
                )
            else:
                file_path = actual_path
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Rename failed after retries, saved at: {actual_path.name}",
                )
        else:
            # No drift — save in place
            file_path = actual_path
            note.metadata.last_known_path = str(file_path.resolve())
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(note.to_dict(), f, indent=2)

        new_mtime = file_path.stat().st_mtime
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"Saved note: {file_path} (mtime: {new_mtime})",
        )
        return new_mtime

    except Exception as e:
        sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Failed to update note: {e}")
        return None


def delete_note(db: FileIndex, note_id: str) -> bool:
    """Deletes the file. Watcher handles DB cleanup."""
    try:
        meta = db.get_metadata(note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.WARNING,
                f"Note not found for delete: {note_id}",
            )
            return False

        file_path = meta.note_dir / generate_filename(meta.note_title, note_id)
        if file_path.exists():
            file_path.unlink()
            sys_log.log(
                LogSource.SYSTEM, LogLevel.INFO, f"Deleted note file: {file_path}"
            )
            return True
        return False
    except Exception as e:
        sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Failed to delete note: {e}")
        return False


# ==========================================
# Directory CRUD Operations
# ==========================================


def create_directory(parent_path: str, dir_name: str) -> Optional[Path]:
    """Creates a new directory on disk."""
    try:
        new_dir = Path(parent_path) / dir_name
        new_dir.mkdir(exist_ok=True)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Created directory: {new_dir}")
        return new_dir
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM, LogLevel.ERROR, f"Failed to create directory: {e}"
        )
        return None


def update_directory_name(old_path: str, new_name: str) -> Optional[Path]:
    """Renames a directory on disk."""
    try:
        old = Path(old_path)
        new = old.parent / new_name
        old.rename(new)
        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"Renamed directory: {old} -> {new}"
        )
        return new
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM, LogLevel.ERROR, f"Failed to rename directory: {e}"
        )
        return None


def delete_directory(dir_path: str) -> bool:
    """Deletes a directory and all its contents from disk."""
    try:
        path = Path(dir_path)
        if path.exists():
            shutil.rmtree(path)
            sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Deleted directory: {path}")
            return True
        return False
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM, LogLevel.ERROR, f"Failed to delete directory: {e}"
        )
        return False
