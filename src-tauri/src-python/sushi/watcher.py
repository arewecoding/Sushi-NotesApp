"""
Sushi Vault Watcher
====================
Filesystem observer that monitors the vault directory for changes.
Updates the CacheDB and notifies the VaultService of events.
"""

import ijson
import os
import time
import uuid
from typing import Union, Callable, Optional
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from sushi.cache_db import FileIndex, NoteMetadata, DirectoryMetadata
from sushi.filesys import (
    load_jnote,
    save_jnote,
    extract_short_id,
    generate_filename,
)
from sushi.logger import sys_log, LogSource, LogLevel


# ==========================================
# Vault Event Handler
# ==========================================


class VaultEventHandler(FileSystemEventHandler):
    """
    Handles all file system events and updates the CacheDB accordingly.
    This acts as the ONLY writer to the DB for structure changes.
    """

    def __init__(self):
        # Injected by VaultService
        self.db: Optional[FileIndex] = None
        self.on_file_event_callback: Optional[Callable[[str, float], None]] = None

    def _notify_active_state(self, path: Path, mtime: float = None):
        """
        Helper to safely fire the callback for ANY path (Note or Directory).
        """
        if not self.on_file_event_callback:
            return

        if mtime is None:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                mtime = 0.0

        try:
            self.on_file_event_callback(str(path), mtime)
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Callback failed for {path}: {e}"
            )

    def _process_note_file(self, file_path: Path):
        """
        Common logic to Register/Update a note in DB and Notify ActiveState.
        Always runs identity resolution first to catch copies.
        """
        result = self._resolve_identity(file_path)
        if result is True:
            # COPY detected — file was renamed, watcher will pick up the new file
            return
        if result is None:
            # Failed to read — skip processing entirely
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.WARNING,
                f"Skipping note (unreadable): {file_path}",
            )
            return

        # Normal registration — identity is verified
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

        self._notify_active_state(file_path)

    def _resolve_identity(self, file_path: Path) -> Optional[bool]:
        """
        Detects if a .jnote file at file_path is a MOVE or COPY.
        Returns:
            False  — Normal/Move, proceed with registration
            True   — Copy detected, file renamed (skip processing)
            None   — Failed to read file (skip processing entirely)
        """
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
            # MOVE — old file is gone
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"MOVE detected: {last_known} -> {current_path}",
            )
            note.metadata.last_known_path = current_path
            save_jnote(file_path, note)
            return False
        else:
            # COPY — old file still exists at last_known_path
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
            save_jnote(file_path, note)
            file_path.rename(new_file)
            return True  # Watcher will pick up the rename as a new event

    # ==========================================
    # Watchdog Event Handlers
    # ==========================================

    def on_created(self, event):
        """Updates DB and notifies ActiveState on file creation events."""
        path = Path(event.src_path)
        sys_log.log(LogSource.SYSTEM, LogLevel.DEBUG, f"Created: {path}")

        if event.is_directory:
            dir_meta = DirectoryMetadata(
                dir_path=path, dir_name=path.name, parent_path=path.parent
            )
            self.db.add_directory(dir_meta)
            self._notify_active_state(path)
        elif path.suffix == ".jnote":
            self._process_note_file(path)

    def on_deleted(self, event):
        """Updates DB and notifies ActiveState on file deletion events."""
        path = Path(event.src_path)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Deleted event: {path}")

        # On Windows, event.is_directory may be False for deleted directories
        # because the directory no longer exists when the event fires.
        is_dir = event.is_directory
        if not is_dir and self.db:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT 1 FROM directories WHERE dir_path = ?", (str(path),))
            is_dir = cursor.fetchone() is not None

        # No extension = likely a directory
        if not is_dir and path.suffix == "":
            is_dir = True

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"Deleted path determined to be directory: {is_dir}",
        )

        if is_dir:
            self.db.delete_directory_recursive(str(path))
            self._notify_active_state(path, mtime=0.0)
        elif path.suffix == ".jnote":
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
                self.db.delete_note(matches[0].note_id)
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Deleted note from DB: {matches[0].note_title}",
                )
            elif len(matches) > 1:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Short ID collision for '{short_id}' — {len(matches)} matches. Triggering rescan.",
                )
                if self.on_file_event_callback:
                    self.on_file_event_callback("__RESCAN__", 0.0)
                return
            else:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.DEBUG,
                    f"No DB match for deleted file: {path.name}",
                )

            self._notify_active_state(path, mtime=0.0)

    def on_modified(self, event):
        """Updates DB and notifies ActiveState on file modification events."""
        if event.is_directory:
            return
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

            self._process_note_file(new_path)
            # Signal a structural move (mtime=-1) so tree updates
            self._notify_active_state(new_path, mtime=-1.0)


# ==========================================
# Vault Watcher (Observer Service)
# ==========================================


class VaultWatcher:
    """Manages the watchdog file system observer."""

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
        """Wipes and rebuilds the DB index from disk."""
        db.clear_all()
        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"Scanning vault: {self.root_path}"
        )

        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)

            # Register directories (skip the root itself)
            if root_path != self.root_path:
                dir_meta = DirectoryMetadata(
                    dir_path=root_path,
                    dir_name=root_path.name,
                    parent_path=root_path.parent,
                )
                db.add_directory(dir_meta)

            # Register notes
            for file in files:
                if file.endswith(".jnote"):
                    file_path = root_path / file
                    meta = self.extract_note_metadata(file_path)
                    if meta:
                        db.add_metadata(meta)

        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Initial scan complete.")

    @staticmethod
    def extract_note_metadata(file_path: Path) -> Optional[NoteMetadata]:
        """Efficiently reads just the 'metadata' key from the JSON using ijson."""
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
