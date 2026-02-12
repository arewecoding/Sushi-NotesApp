import json
import ijson
import os
import re
import shutil
import uuid
from typing import Union, Callable, Optional
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Use the sushi package imports ---
from sushi.cache_db import FileIndex, NoteMetadata, DirectoryMetadata
from sushi.note_schema import JNote
from sushi.logger_service import sys_log, LogSource, LogLevel


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
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove anything that isn't alphanumeric or hyphen
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate to max length (break at hyphen boundary if possible)
    if len(slug) > max_len:
        slug = slug[:max_len]
        # Don't cut mid-word: trim back to last hyphen
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
    stem = Path(filename).stem  # 'my-cool-note-4f1139b'
    if len(stem) < SHORT_ID_LEN:
        return None
    short_id = stem[-SHORT_ID_LEN:]
    # Validate it looks like a hex/uuid fragment
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

    return expected_path  # Return expected path even if missing (caller handles error)


# ==========================================
# Vault Watcher
# ==========================================


class VaultEventHandler(FileSystemEventHandler):
    """
    Handles all file system events and updates the CacheDB accordingly.
    This acts as the ONLY writer to the DB for structure changes.
    """

    def __init__(self):
        """
        These will be injected by VaultService
        """
        self.db: Optional[FileIndex] = None
        self.on_file_event_callback: Optional[Callable[[str, float], None]] = None

    def _get_note_meta(file_path: str):
        """
        Helper to extract metadata efficiently.
        """
        return VaultWatcher.extract_note_metadata(Path(file_path))

    def _notify_active_state(self, path: Path, mtime: float = None):
        """
        Helper to safely fire the callback for ANY path (Note or Directory)
        """
        if not self.on_file_event_callback:
            return

        # Get modification time if not provided
        if mtime is None:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                mtime = 0.0

        try:
            self.on_file_event_callback(str(path), mtime)
        except Exception as e:
            # Don't crash the watcher if callback fails
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Callback failed for {path}: {e}"
            )

    def _process_note_file(self, file_path: Path):
        """
        Common logic to Register/Update a note in DB and Notify ActiveState.
        Always runs identity resolution first to catch copies.
        """
        # Step 1: Resolve identity (move vs copy)
        result = self._resolve_identity(file_path)
        if result is True:
            # COPY detected — file was renamed, watcher will pick up the new file
            return
        if result is None:
            # Failed to read — skip processing entirely to avoid clobbering
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.WARNING,
                f"Skipping note (unreadable): {file_path}",
            )
            return

        # Step 2: Normal registration — identity is verified
        meta = VaultWatcher.extract_note_metadata(file_path)
        if meta:
            self.db.add_metadata(meta)
            sys_log.log(
                LogSource.DB, LogLevel.INFO, f"Registered note: {meta.note_title}"
            )
        else:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.WARNING, f"Could not parse note: {file_path}"
            )

        # Notify ActiveState about this file event
        self._notify_active_state(file_path)

    def _resolve_identity(self, file_path: Path) -> Optional[bool]:
        """
        Detects if a .jnote file at file_path is a MOVE or COPY.
        Returns:
            False  — Normal/Move, proceed with registration
            True   — Copy detected, file renamed (skip processing)
            None   — Failed to read file (skip processing entirely)
        """
        import time

        # Retry up to 3 times with delay for Windows file locks
        note = None
        for attempt in range(3):
            note = load_jnote(file_path)
            if note is not None:
                break
            if attempt < 2:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.DEBUG,
                    f"Retry {attempt + 1}/3 reading {file_path.name}...",
                )
                time.sleep(0.5)

        if not note:
            return None  # Unreadable after retries

        current_path = str(file_path.resolve())
        last_known = note.metadata.last_known_path

        # Case A: Path matches or first time (no last_known_path yet)
        if last_known is None or last_known == current_path:
            if last_known is None:
                # First time — stamp the path
                note.metadata.last_known_path = current_path
                save_jnote(file_path, note)
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.DEBUG,
                    f"Stamped last_known_path on {file_path.name}",
                )
            return False

        # Case B: Path mismatch — determine move vs copy
        old_path = Path(last_known)

        if not old_path.exists():
            # Scenario 1: MOVE — old file is gone
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"MOVE detected: {last_known} -> {current_path}",
            )
            note.metadata.last_known_path = current_path
            save_jnote(file_path, note)
            return False  # Keep UUID
        else:
            # Scenario 2: COPY — old file still exists at last_known_path
            old_uuid = note.metadata.note_id
            new_uuid = str(uuid.uuid4())
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"COPY detected: Assigning new UUID {new_uuid} (was {old_uuid})",
            )
            note.metadata.note_id = new_uuid
            new_name = generate_filename(note.metadata.title, new_uuid)
            new_file = file_path.parent / new_name
            note.metadata.last_known_path = str(new_file.resolve())
            # Save with new identity, then rename to match
            save_jnote(file_path, note)
            file_path.rename(new_file)
            return True  # Watcher will pick up the rename as a new event

    def on_created(self, event):
        """
        Updates DB and notifies ActiveState on file creation events.
        """
        path = Path(event.src_path)
        sys_log.log(LogSource.SYSTEM, LogLevel.DEBUG, f"Created: {path}")

        if event.is_directory:
            dir_meta = DirectoryMetadata(
                dir_path=path, dir_name=path.name, parent_path=path.parent
            )
            self.db.add_directory(dir_meta)
            # Notify ActiveFileTree
            self._notify_active_state(path)
        elif path.suffix == ".jnote":
            self._process_note_file(path)

    def on_deleted(self, event):
        """
        Updates DB and notifies ActiveState on file deletion events.
        """
        path = Path(event.src_path)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Deleted event: {path}")

        # On Windows, event.is_directory may be False for deleted directories
        # because the directory no longer exists when the event fires.
        # We need to check our DB or use path characteristics to determine type.

        # Check if this path was a known directory in our DB
        is_dir = event.is_directory
        if not is_dir and self.db:
            # Query DB to see if we have this as a directory
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT 1 FROM directories WHERE dir_path = ?", (str(path),))
            is_dir = cursor.fetchone() is not None

        # Also check: if path has no suffix (no file extension), it's likely a directory
        if not is_dir and path.suffix == "":
            is_dir = True

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"Deleted path determined to be directory: {is_dir}",
        )

        if is_dir:
            self.db.delete_directory_recursive(str(path))
            # Notify ActiveFileTree of deletion
            self._notify_active_state(path, mtime=0.0)  # mtime 0 indicates deletion
        elif path.suffix == ".jnote":
            # Extract short ID from the filename and look up in DB
            short_id = extract_short_id(path.name)
            if not short_id:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Could not extract short_id from: {path.name}",
                )
                return

            matches = self.db.get_metadata_by_short_id(short_id, str(path.parent))

            if len(matches) == 1:
                # Safe — exactly one match
                self.db.delete_note(matches[0].note_id)
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Deleted note from DB: {matches[0].note_title}",
                )
            elif len(matches) > 1:
                # COLLISION — do NOT delete, trigger rescan
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Short ID collision for '{short_id}' — {len(matches)} matches. Triggering rescan.",
                )
                # Rescan is handled by the VaultService via callback
                if self.on_file_event_callback:
                    self.on_file_event_callback("__RESCAN__", 0.0)
                return
            else:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.DEBUG,
                    f"No DB match for deleted file: {path.name}",
                )

            # Notify ActiveNote if it's open
            self._notify_active_state(path, mtime=0.0)

    def on_modified(self, event):
        """
        Updates DB and notifies ActiveState on file modification events.
        """
        if event.is_directory:
            return  # Ignore directory modification events
        path = Path(event.src_path)
        if path.suffix == ".jnote":
            self._process_note_file(path)

    def on_moved(self, event):
        """
        Updates DB and notifies ActiveState on file move events.
        Also stamps last_known_path on the moved .jnote file.
        """
        old_path = Path(event.src_path)
        new_path = Path(event.dest_path)
        sys_log.log(
            LogSource.SYSTEM, LogLevel.DEBUG, f"Moved: {old_path} -> {new_path}"
        )

        if event.is_directory:
            self.db.update_directory(str(old_path), str(new_path), new_path.name)
            self._notify_active_state(new_path)
        elif new_path.suffix == ".jnote":
            # Update last_known_path only if it doesn't already match
            # (update_note drift-rename already stamps the correct path)
            note = load_jnote(new_path)
            if note:
                resolved = str(new_path.resolve())
                if note.metadata.last_known_path != resolved:
                    note.metadata.last_known_path = resolved
                    save_jnote(new_path, note)

            # Delete old DB entry using short_id from old filename
            old_short_id = extract_short_id(old_path.name)
            if old_short_id:
                old_matches = self.db.get_metadata_by_short_id(
                    old_short_id, str(old_path.parent)
                )
                if len(old_matches) == 1:
                    self.db.delete_note(old_matches[0].note_id)
                # If >1 match (collision) or 0 matches, skip delete — rescan will fix

            self._process_note_file(new_path)
            # Signal a structural move (mtime=-1) so tree updates
            self._notify_active_state(new_path, mtime=-1.0)


class VaultWatcher:
    """Singleton service that manages the file system observer."""

    def __init__(self, root_path: Union[str, Path]):
        self.root_path = Path(root_path)
        self.observer = Observer()
        self.handler = VaultEventHandler()

    def start(self):
        if not self.root_path.exists():
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Vault path does not exist: {self.root_path}",
            )
            return

        self.observer.schedule(self.handler, str(self.root_path), recursive=True)
        self.observer.start()
        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"Watcher started for: {self.root_path}"
        )

    def stop(self):
        self.observer.stop()
        self.observer.join()
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Watcher stopped.")

    def scan(self, db: FileIndex):
        """
        Wipes (optionally) and rebuilds the DB index from disk.
        """
        db.clear_all()
        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"Scanning vault: {self.root_path}"
        )

        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)

            # Register Directories (skip the root itself)
            if root_path != self.root_path:
                dir_meta = DirectoryMetadata(
                    dir_path=root_path,
                    dir_name=root_path.name,
                    parent_path=root_path.parent,
                )
                db.add_directory(dir_meta)

            # Register Notes
            for file in files:
                if file.endswith(".jnote"):
                    file_path = root_path / file
                    meta = self.extract_note_metadata(file_path)
                    if meta:
                        db.add_metadata(meta)

        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Initial scan complete.")

    @staticmethod
    def extract_note_metadata(file_path: Path) -> Optional[NoteMetadata]:
        """
        Efficiently reads just the 'metadata' key from the JSON using ijson.
        """
        try:
            with open(file_path, "rb") as f:
                parser = ijson.items(f, "metadata", use_float=True)
                for metadata in parser:
                    return NoteMetadata(
                        note_id=metadata.get("note_id", file_path.stem),
                        note_title=metadata.get("title", "Untitled"),
                        note_version=metadata.get("version", "1.0"),
                        note_dir=file_path.parent,
                    )
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Failed to parse {file_path}: {e}"
            )
        return None


# ==========================================
# CRUD Operations (Filesystem Only)
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

        # Stamp last_known_path before first save
        note.metadata.last_known_path = str(file_path.resolve())

        # Save to disk
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

        # Find the ACTUAL file on disk (may have stale name)
        actual_path = get_note_filepath(db, meta.note_id)
        if not actual_path or not actual_path.exists():
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Note file not found on disk for: {meta.note_id}",
            )
            return None

        # Derive expected filename from the NEW title being saved
        expected_filename = generate_filename(note.metadata.title, meta.note_id)
        expected_path = meta.note_dir / expected_filename

        # Update timestamp
        note.metadata.update_timestamp()

        # Drift detection: actual filename != expected → save then rename
        if actual_path.name != expected_filename:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"Title drift: renaming {actual_path.name} -> {expected_filename}",
            )

            # Step 1: Save content with last_known_path pointing to CURRENT path
            # This prevents _resolve_identity from seeing a phantom MOVE
            note.metadata.last_known_path = str(actual_path.resolve())
            with open(actual_path, "w", encoding="utf-8") as f:
                json.dump(note.to_dict(), f, indent=2)

            # Step 2: Rename with retry (watchdog may briefly hold the file)
            import time

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
                # Step 3: Update last_known_path in the renamed file
                note.metadata.last_known_path = str(expected_path.resolve())
                save_jnote(expected_path, note)
                file_path = expected_path
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Rename succeeded: {expected_filename}",
                )
            else:
                # Rename failed — content is saved at actual path, that's OK
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

        # Return the new modification time for echo suppression
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
# Directory CRUD (Filesystem Only)
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
