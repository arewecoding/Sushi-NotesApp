import json
import ijson
import os
import shutil
import time
from typing import Union, Callable, Optional, Dict, Any
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Use the sushi package imports ---
from sushi.cache_db import FileIndex, NoteMetadata, DirectoryMetadata
from sushi.note_schema import JNote
from sushi.logger_service import sys_log, LogSource, LogLevel


# ==========================================
# Vault Watcher
# ==========================================


class VaultEventHandler(FileSystemEventHandler):
    """
    Handles all file system events and updates the CacheDB accordingly.
    This acts as the ONLY writer to the DB for structure changes.
    """

    def __init__(self):
        # These will be injected by VaultService
        self.db: Optional[FileIndex] = None
        self.on_file_event_callback: Optional[Callable[[str, float], None]] = None

    # Helper to extract metadata efficiently.
    def _get_note_meta(file_path: str):
        return VaultWatcher.extract_note_metadata(Path(file_path))

    #
    #     Helper to safely fire the callback for ANY path (Note or Directory).
    #
    def _notify_active_state(self, path: Path, mtime: float = None):
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

    #
    #     Common logic to Register/Update a note in DB and Notify ActiveState.
    #
    def _process_note_file(self, file_path: Path):
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

        # Notify ActiveState about this file event (even if parse failed, it might fix itself)
        self._notify_active_state(file_path)

    def on_created(self, event):
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
            # Extract note_id from the filename (assumes <uuid>.jnote format)
            note_id = path.stem
            self.db.delete_note(note_id)
            # Notify ActiveNote if it's open
            self._notify_active_state(path, mtime=0.0)

    def on_modified(self, event):
        if event.is_directory:
            return  # Ignore directory modification events
        path = Path(event.src_path)
        if path.suffix == ".jnote":
            self._process_note_file(path)

    def on_moved(self, event):
        # Handles renames and moves
        old_path = Path(event.src_path)
        new_path = Path(event.dest_path)
        sys_log.log(
            LogSource.SYSTEM, LogLevel.DEBUG, f"Moved: {old_path} -> {new_path}"
        )

        if event.is_directory:
            self.db.update_directory(str(old_path), str(new_path), new_path.name)
            self._notify_active_state(new_path)
        elif new_path.suffix == ".jnote":
            # Treat as delete old + create new
            self.db.delete_note(old_path.stem)
            self._process_note_file(new_path)


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

    #
    #     Wipes (optionally) and rebuilds the DB index from disk.
    #
    def scan(self, db: FileIndex):
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

    #
    #     Efficiently reads just the 'metadata' key from the JSON using ijson.
    #
    @staticmethod
    def extract_note_metadata(file_path: Path) -> Optional[NoteMetadata]:
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


#
#     Creates a JNote object, saves it to disk.
#     Watcher will handle the DB update.
#
def create_new_note(base_dir: str, title: str = "Untitled Note") -> Optional[JNote]:
    """Creates a new JNote and saves it to disk."""
    try:
        note = JNote.create_new(title)
        note_id = note.metadata.note_id
        file_path = Path(base_dir) / f"{note_id}.jnote"

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


#
#     Overwrites the file on disk with the provided JNote object.
#     RETURNS timestamp for Echo Suppression.
#
def update_note(db: FileIndex, note: JNote) -> Optional[float]:
    """Updates a note on disk and returns the new mtime."""
    try:
        meta = db.get_metadata(note.metadata.note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Note not found in DB: {note.metadata.note_id}",
            )
            return None

        file_path = meta.note_dir / f"{meta.note_id}.jnote"

        # Update the timestamp before saving
        note.metadata.update_timestamp()

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


#
#     Deletes the file. Watcher handles DB cleanup.
#
def delete_note(db: FileIndex, note_id: str) -> bool:
    """Deletes a note file from disk."""
    try:
        meta = db.get_metadata(note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.WARNING,
                f"Note not found for delete: {note_id}",
            )
            return False

        file_path = meta.note_dir / f"{note_id}.jnote"
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
