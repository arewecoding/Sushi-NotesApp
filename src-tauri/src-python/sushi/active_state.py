import threading
from typing import Dict, Optional, Any, Union
from pathlib import Path  # NECESSARY CHANGE: Added for safe path handling
import json

# --- Architecture Imports ---
from sushi.filesys import VaultWatcher, update_note, create_new_note
from sushi.note_schema import JNote
from sushi.block_factory import BlockFactory
from sushi.cache_db import FileIndex, NoteMetadata
from sushi.logger_service import sys_log, LogSource, LogLevel
from sushi.ipc_models import PyTauriModel

# PyTauri imports for event emission (type hints only to avoid import errors)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytauri import AppHandle

# Try to import Emitter at runtime, but don't fail on import
try:
    from pytauri import Emitter, AppHandle as AppHandleType

    HAS_EMITTER = True
except ImportError:
    HAS_EMITTER = False
    AppHandleType = None


# ==========================================
# Event Payloads for Frontend
# ==========================================


class TreeChangedPayload(PyTauriModel):
    """Payload for tree-changed event."""

    changed_path: str
    event_type: str  # 'created', 'deleted', 'moved'


class NoteContentChangedPayload(PyTauriModel):
    """Payload for note-content-changed event (external edits)."""

    note_id: str


# ==========================================
# 1. Active File Tree (Navigation State)
# ==========================================


class ActiveFileTree:
    """
    Manages the state of the navigation sidebar.
    Currently, the 'Source of Truth' is the SQLite CacheDB.
    This class listens for structural changes (Dir Created/Deleted)
    and signals the Frontend to refresh the view via Tauri events.
    """

    def __init__(self, app_handle: Optional["AppHandle"] = None):
        self.needs_refresh = False
        self._app_handle = app_handle

    def set_app_handle(self, app_handle: "AppHandle"):
        """Set AppHandle for event emission (called after VaultService is registered)."""
        self._app_handle = app_handle

    def handle_structure_change(self, path: str, event_type: str = "modified"):
        """
        Called when a Directory is created, moved, or deleted.
        Emits a tree-changed event to the frontend.
        """
        self.needs_refresh = True
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"File tree changed: {path} ({event_type})",
        )

        # Emit event to frontend
        if HAS_EMITTER and self._app_handle is not None:
            try:
                Emitter.emit(
                    self._app_handle,
                    "tree-changed",
                    TreeChangedPayload(changed_path=path, event_type=event_type),
                )
                sys_log.log(
                    LogSource.SYSTEM, LogLevel.DEBUG, "Emitted tree-changed event"
                )
            except Exception as e:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.ERROR,
                    f"Failed to emit tree-changed: {e}",
                )


# ==========================================
# 2. Active Note (Memory State)
# ==========================================


class ActiveNote:
    """
    Represents a single open note in memory.
    Uses strict JNote objects and the Filesys module for I/O.
    Implements 'Echo Suppression' to handle local vs external edits.
    """

    def __init__(self, note_id: str, service: "VaultService"):
        self.note_id = note_id
        self.service = service
        self.note_obj: Optional[JNote] = None
        self.is_dirty = False

        # Echo Suppression: When we save, we record the expected mtime.
        # If a watcher event arrives with that exact mtime, we ignore it.
        self._last_save_mtime: Optional[float] = None

        # Auto-save timer
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._SAVE_DELAY = 2.5  # seconds

        # Load the note immediately
        self._load_from_disk_sync()

        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"ActiveNote created for: {note_id}"
        )

    # ==========================================
    # Loading
    # ==========================================

    # Initial blocking load.
    def _load_from_disk_sync(self):
        meta = self.service.db.get_metadata(self.note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Cannot load note {self.note_id}: not found in DB",
            )
            return

        file_path = meta.note_dir / f"{self.note_id}.jnote"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self.note_obj = JNote.from_dict(raw_data, str(file_path))
            if self.note_obj:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Loaded note: {self.note_obj.metadata.title}",
                )
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Failed to load note {file_path}: {e}",
            )

    # ==========================================
    # External Update Handling (Echo Suppression)
    # ==========================================

    #
    #     Called by VaultService when Watcher barks.
    #
    def handle_external_update(self, event_mtime: float):
        # Suppress if this is our own save echoing back
        if self._last_save_mtime and abs(event_mtime - self._last_save_mtime) < 0.1:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.DEBUG, f"Suppressed echo for {self.note_id}"
            )
            return

        # It's an external change - trigger a hot swap
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            f"External change detected for {self.note_id}",
        )
        self._trigger_hot_swap()

    # Reloads data in a thread.
    def _trigger_hot_swap(self):
        # Run reload in a background thread to not block
        thread = threading.Thread(target=self._perform_hot_swap, daemon=True)
        thread.start()

    def _perform_hot_swap(self):
        meta = self.service.db.get_metadata(self.note_id)
        if not meta:
            return

        file_path = meta.note_dir / f"{self.note_id}.jnote"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            new_note = JNote.from_dict(raw_data, str(file_path))

            if new_note:
                # Swap the data (atomic as possible)
                old_title = self.note_obj.metadata.title if self.note_obj else "Unknown"
                self.note_obj = new_note
                self.is_dirty = False

                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Hot-swapped note: {old_title} -> {new_note.metadata.title}",
                )

                # Emit event to frontend for UI refresh
                app_handle = self.service._app_handle
                if HAS_EMITTER and app_handle is not None:
                    try:
                        Emitter.emit(
                            app_handle,
                            "note-content-changed",
                            NoteContentChangedPayload(note_id=self.note_id),
                        )
                        sys_log.log(
                            LogSource.SYSTEM,
                            LogLevel.DEBUG,
                            f"Emitted note-content-changed for {self.note_id}",
                        )
                    except Exception as emit_err:
                        sys_log.log(
                            LogSource.SYSTEM,
                            LogLevel.ERROR,
                            f"Failed to emit note-content-changed: {emit_err}",
                        )
        except Exception as e:
            sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Hot swap failed: {e}")

    # ==========================================
    # Block Editing (Facade to BlockFactory)
    # ==========================================

    # Uses BlockFactory to append a new block.
    def add_block(self, block_type: str, **kwargs):
        if not self.note_obj:
            return

        new_block = BlockFactory.create(block_type, **kwargs)
        self.note_obj.blocks.append(new_block)
        self.is_dirty = True
        self._schedule_save()

    def update_block(self, block_id: str, new_data: Dict[str, Any]):
        if not self.note_obj:
            return

        for block in self.note_obj.blocks:
            if block.block_id == block_id:
                block.data.update(new_data)
                self.is_dirty = True
                self._schedule_save()
                return
        sys_log.log(LogSource.SYSTEM, LogLevel.WARNING, f"Block not found: {block_id}")

    def delete_block(self, block_id: str):
        if not self.note_obj:
            return

        self.note_obj.blocks = [
            b for b in self.note_obj.blocks if b.block_id != block_id
        ]
        self.is_dirty = True
        self._schedule_save()

    def update_content(self, title: str, blocks: list):
        """
        Updates the entire note content (title and blocks).
        Called from frontend when user edits the note.
        """
        if not self.note_obj:
            return False

        # Update title
        self.note_obj.metadata.title = title
        self.note_obj.metadata.update_timestamp()

        # Update blocks - convert from dict list to NoteBlock objects
        from sushi.note_schema import NoteBlock

        new_blocks = []
        for block_dict in blocks:
            # Handle camelCase from frontend
            block_data = {
                "block_id": block_dict.get("blockId") or block_dict.get("block_id"),
                "type": block_dict.get("type"),
                "data": block_dict.get("data", {}),
                "version": block_dict.get("version", "1.0"),
                "tags": block_dict.get("tags", []),
                "backlinks": block_dict.get("backlinks", []),
            }
            new_blocks.append(NoteBlock.from_dict(block_data))

        self.note_obj.blocks = new_blocks
        self.is_dirty = True
        self._schedule_save()

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"Updated note content: {title} ({len(blocks)} blocks)",
        )
        return True

    # ==========================================
    # Auto-Save Logic
    # ==========================================

    def _schedule_save(self):
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(self._SAVE_DELAY, self._save_to_disk)
            self._save_timer.start()

    def _save_to_disk(self):
        if not self.is_dirty or not self.note_obj:
            return

        new_mtime = update_note(self.service.db, self.note_obj)
        if new_mtime:
            self._last_save_mtime = new_mtime
            self.is_dirty = False
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"Auto-saved: {self.note_obj.metadata.title}",
            )

    def close(self):
        # Flush any pending save
        if self._save_timer:
            self._save_timer.cancel()
        if self.is_dirty:
            self._save_to_disk()


# ==========================================
# 3. Vault Service (The Brain)
# ==========================================
# NECESSARY CHANGE: Renamed StateManager to VaultService and removed Singleton for Dependency Injection


class VaultService:
    """
    The Single Source of Truth for the application.
    It holds the Database, the File Watcher, and all Active Notes.
    Replaces the old singleton StateManager.
    """

    def __init__(
        self, vault_path: Union[str, Path], app_handle: Optional["AppHandle"] = None
    ):
        self.vault_path = Path(vault_path)
        self._app_handle = app_handle

        # Core Components
        self.db = FileIndex()  # In-memory SQLite by default
        self.watcher = VaultWatcher(self.vault_path)
        self.file_tree = ActiveFileTree(app_handle)

        # Active Notes Registry
        self._active_notes: Dict[str, ActiveNote] = {}

        # Wire up the event handler
        self.watcher.handler.db = self.db
        self.watcher.handler.on_file_event_callback = self.on_file_event

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            f"VaultService initialized for: {self.vault_path}",
        )

    def set_app_handle(self, app_handle: "AppHandle"):
        """Update AppHandle for event emission after registration."""
        self._app_handle = app_handle
        self.file_tree.set_app_handle(app_handle)

    # Starts the machinery.
    def start(self):
        # Initial scan to populate DB
        self.watcher.scan(self.db)
        # Start watching for changes
        self.watcher.start()
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "VaultService started.")

    # Stops the machinery.
    def stop(self):
        self.watcher.stop()
        # Close all active notes
        for note_id in list(self._active_notes.keys()):
            self.close_note(note_id)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "VaultService stopped.")

    #
    #     Callback triggered by VaultWatcher.
    #
    def on_file_event(self, path_str: str, mtime: float):
        path = Path(path_str)

        # Determine event type from mtime
        # mtime=0 means the file was deleted (set by VaultEventHandler.on_deleted)
        if mtime == 0.0:
            event_type = "deleted"
        elif path.exists():
            event_type = "modified"
        else:
            event_type = "created"

        # If it's a directory or non-note file, update file tree
        if path.is_dir() or path.suffix != ".jnote":
            self.file_tree.handle_structure_change(path_str, event_type)
            return

        # For note files, also trigger tree update so sidebar refreshes
        self.file_tree.handle_structure_change(path_str, event_type)

        # If it's a note file, notify the corresponding ActiveNote
        note_id = path.stem
        if note_id in self._active_notes:
            self._active_notes[note_id].handle_external_update(mtime)

    # ==========================================
    # Note Operations (Business Logic)
    # ==========================================

    # Fetch file tree from the DB.
    def get_sidebar_data(self):
        return self.db.get_all_notes()

    #
    #     Creates a note on disk and returns the metadata object.
    #     This handles the logic manually since filesys.py doesn't have create_new_note yet.
    #
    def create_note(self, title: str) -> Optional[NoteMetadata]:
        note = create_new_note(str(self.vault_path), title)
        if not note:
            return None

        # The watcher will pick up the new file, but we can return the metadata immediately
        meta = NoteMetadata(
            note_id=note.metadata.note_id,
            note_title=note.metadata.title,
            note_version=note.metadata.version,
            note_dir=self.vault_path,
        )
        return meta

    def get_or_open_note(self, note_id: str) -> Optional[ActiveNote]:
        # Return existing if already open
        if note_id in self._active_notes:
            return self._active_notes[note_id]

        # Open new
        active_note = ActiveNote(note_id, self)
        if active_note.note_obj:
            self._active_notes[note_id] = active_note
            return active_note
        return None

    def close_note(self, note_id: str):
        if note_id in self._active_notes:
            self._active_notes[note_id].close()
            del self._active_notes[note_id]
            sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Closed note: {note_id}")


# NECESSARY CHANGE: Removed global 'state_manager' instance
