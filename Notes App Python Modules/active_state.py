import threading
from typing import Dict, Optional, Any, Union
from pathlib import Path  # NECESSARY CHANGE: Added for safe path handling
import json

# --- Architecture Imports ---
# NECESSARY CHANGE: Updated imports to match the new package structure and dependency injection
from tauri_app.filesys import VaultWatcher, FileIndex, update_note
from tauri_app.note_schema import JNote
from tauri_app.block_factory import BlockFactory
from tauri_app.cache_db import NoteMetadata
from tauri_app.logger_service import sys_log, LogSource, LogLevel


# ==========================================
# 1. Active File Tree (Navigation State)
# ==========================================
class ActiveFileTree:
    """
    Manages the state of the navigation sidebar.
    Currently, the 'Source of Truth' is the SQLite CacheDB.
    This class listens for structural changes (Dir Created/Deleted)
    and signals the Frontend to refresh the view.
    """

    def __init__(self):
        self.needs_refresh = False

    def handle_structure_change(self, path: str):
        """
        Called when a Directory is created, moved, or deleted.
        """
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "File Tree Structure changed. Refreshing...", meta={"path": path})
        self.needs_refresh = True

        # TODO: EMIT SIGNAL TO FRONTEND
        # e.g., pytauri.emit("refresh_file_tree")


# ==========================================
# 2. Active Note (Memory State)
# ==========================================
class ActiveNote:
    """
    Represents a single open note in memory.
    Uses strict JNote objects and the Filesys module for I/O.
    Implements 'Echo Suppression' to handle local vs external edits.
    """

    # NECESSARY CHANGE: Inject 'service' to access DB and Watcher
    def __init__(self, note_id: str, service: 'VaultService'):
        self.note_id = note_id
        self.service = service  # Hold reference to the main service

        # 1. Resolve Path via CacheDB (Accessed via Service)
        # NECESSARY CHANGE: Use injected DB instead of global localdb
        meta = self.service.db.get_metadata(note_id)
        if not meta:
            raise ValueError(f"Note ID {note_id} not found in Index.")

        self.file_path = meta.note_dir / f"{note_id}.jnote"
        self.abs_path_str = str(self.file_path.resolve())

        # 2. State & Data
        self.note_obj: Optional[JNote] = None
        self._lock = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None
        self.is_dirty = False

        # 3. Echo Suppression (The Filter)
        self.last_known_mtime = 0.0

        # 4. Initial Load
        self._load_from_disk_sync()

        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"ActiveNote loaded: {self.note_id}")

    # ----------------------------------
    # Loading & Hot-Swapping
    # ----------------------------------
    def _load_from_disk_sync(self):
        """Initial blocking load."""
        with self._lock:
            # We assume update_note works, but we need READ logic here.
            # Since filesys doesn't have a 'read_note' yet (it relied on ijson for meta),
            # we read raw JSON here and parse via Schema.
            # ideally filesys should handle read too, but this is acceptable for ActiveState.
            try:
                import json
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Parse Strict Object
                self.note_obj = JNote.from_dict(data, str(self.file_path))

                # Capture Timestamp
                self.last_known_mtime = self.file_path.stat().st_mtime

            except Exception as e:
                sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, "Failed to load note",
                            meta={"id": self.note_id, "error": str(e)})
                # Initialize empty if failed to prevent crash
                if not self.note_obj:
                    self.note_obj = JNote.create_new(title="Error Loading Note")

    def handle_external_update(self, event_mtime: float):
        """
        Called by VaultService when Watcher barks.
        """
        # ECHO FILTER: If timestamp matches our last save, ignore it.
        # (Using 0.1s epsilon for float precision safety)
        if abs(event_mtime - self.last_known_mtime) < 0.1:
            return

        # It's a real external change (VS Code, Dropbox, etc.)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"External change detected for {self.note_id}")
        self._trigger_hot_swap()

    def _trigger_hot_swap(self):
        """Reloads data in a thread."""
        if self.is_dirty:
            sys_log.log(LogSource.SYSTEM, LogLevel.WARNING, "Hot-swap aborted: User has unsaved changes.")
            return

        threading.Thread(target=self._perform_hot_swap, daemon=True).start()

    def _perform_hot_swap(self):
        try:
            import json  # Ensure json is imported

            # 1. Heavy I/O (Read Disk) - Done outside lock for responsiveness
            # We accept that the file might change again during this read,
            # but we prioritize not blocking the UI thread.
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 2. Parse Object - Done outside lock
            new_obj = JNote.from_dict(data, str(self.file_path))
            # Get the exact mtime of the file we just read/stat-ed to update our echo suppression
            new_mtime = self.file_path.stat().st_mtime

            # 3. Critical Section (Pointer Flip)
            with self._lock:
                # --- RACE CONDITION FIX ---
                # We must check 'is_dirty' AGAIN inside the lock.
                # Scenario:
                #   1. Thread A starts reading disk (taking 50ms).
                #   2. Thread B (User) types a character -> sets is_dirty = True.
                #   3. Thread A finishes reading and acquires lock.
                # If we don't check here, we would overwrite the user's new character
                # with the old data from disk.
                if self.is_dirty:
                    sys_log.log(LogSource.SYSTEM, LogLevel.WARNING,
                                "Hot-swap aborted: User made changes during disk read.")
                    return

                # If still clean, it's safe to swap
                self.note_obj = new_obj
                self.last_known_mtime = new_mtime

            sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Hot-swap complete.")
            # TODO: Emit 'note_updated' signal to Frontend

        except Exception as e:
            sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, "Hot-swap failed", meta={"error": str(e)})

    # ----------------------------------
    # Block Operations (The Logic)
    # ----------------------------------
    def add_block(self, block_type: str, **kwargs):
        """Uses BlockFactory to append a new block."""
        with self._lock:
            new_block = BlockFactory.create(block_type, **kwargs)
            self.note_obj.blocks.append(new_block)
            self.is_dirty = True

        self._schedule_save()
        return new_block

    def update_block(self, block_id: str, new_data: Dict[str, Any]):
        with self._lock:
            found = False
            for block in self.note_obj.blocks:
                if block.block_id == block_id:
                    block.data = new_data  # Update data container
                    found = True
                    break

            if found:
                self.is_dirty = True
                self._schedule_save()
            else:
                sys_log.log(LogSource.SYSTEM, LogLevel.WARNING, f"Block {block_id} not found in {self.note_id}")

    def delete_block(self, block_id: str):
        with self._lock:
            initial_count = len(self.note_obj.blocks)
            self.note_obj.blocks = [b for b in self.note_obj.blocks if b.block_id != block_id]

            if len(self.note_obj.blocks) < initial_count:
                self.is_dirty = True
                self._schedule_save()

    # ----------------------------------
    # Saving Logic (Delegated to Filesys)
    # ----------------------------------
    def _schedule_save(self):
        if self._save_timer: self._save_timer.cancel()
        self._save_timer = threading.Timer(2.0, self._save_to_disk)
        self._save_timer.start()

    def _save_to_disk(self):
        with self._lock:
            if not self.is_dirty or not self.note_obj:
                return

            # NECESSARY CHANGE: Pass injected DB instance to update_note
            result = update_note(self.service.db, self.note_obj)

            if result["success"]:
                # CAPTURE THE ECHO
                self.last_known_mtime = result["mtime"]
                self.is_dirty = False
            else:
                sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, "Auto-save failed", meta=result)

    def close(self):
        if self._save_timer: self._save_timer.cancel()
        if self.is_dirty: self._save_to_disk()


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

    def __init__(self, vault_path: Union[str, Path]):

        if isinstance(vault_path, str):
            self.vault_path = Path(vault_path)
        else:
            self.vault_path = vault_path

        # 1. Initialize DB (Owned by this service)
        # We create the index in memory for now, matching original behavior
        self.db = FileIndex(":memory:")

        # 2. Initialize Watcher (Owned by this service)
        self.watcher = VaultWatcher(self.vault_path)

        # 3. Active Memory
        self.active_notes: Dict[str, ActiveNote] = {}
        self.file_tree = ActiveFileTree()

        # 4. Wire up the Watcher -> Service communication
        # NECESSARY CHANGE: Manually attach DB and Callback to handler (replaces global register)
        self.watcher.handler.db = self.db
        self.watcher.handler.callback = self.on_file_event

        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"VaultService Initialized for {self.vault_path}")

    def start(self):
        """Starts the machinery."""
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Starting VaultService machinery...")

        # Initial Scan to populate DB
        self.watcher.scan(self.db)

        # Start the observer
        self.watcher.start()

    def stop(self):
        """Stops the machinery."""
        # Close all notes (save them)
        for note in list(self.active_notes.values()):
            note.close()
        self.watcher.stop()
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "VaultService stopped.")

    # ----------------------------------
    # The Event Router
    # ----------------------------------
    def on_file_event(self, path_str: str, mtime: float):
        """
        Callback triggered by VaultWatcher.
        """
        # 1. Is this an Active Note?
        # We need to check if this path belongs to any open note.
        for note in self.active_notes.values():
            if note.abs_path_str == path_str:
                note.handle_external_update(mtime)
                return

        # 2. Is it a Structure Change (Folder)?
        self.file_tree.handle_structure_change(path_str)

    # ----------------------------------
    # API for Frontend / IPC
    # ----------------------------------
    def get_sidebar_data(self) -> Dict[str, Any]:
        """Fetch file tree from the DB."""
        # NECESSARY CHANGE: Expose DB contents for sidebar
        return self.db.get_directory_contents(self.vault_path)

    def create_note(self, title: str) -> NoteMetadata:
        """
        Creates a note on disk and returns the metadata object.
        This handles the logic manually since filesys.py doesn't have create_new_note yet.
        """
        # Create a new JNote object
        new_note = JNote.create_new(title)
        new_id = new_note.metadata.note_id

        # Define Path
        filename = f"{new_id}.jnote"
        file_path = self.vault_path / filename

        try:
            # Write to disk
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(new_note.to_dict(), f, indent=2)

            # Manually force the DB to see it (since watcher might be slow)
            # But normally watcher handles this. We will wait for watcher in main.py

            # Return Metadata immediately so UI can use it
            return new_note.metadata

        except Exception as e:
            raise Exception(f"Failed to create note: {e}")

    def get_or_open_note(self, note_id: str) -> Optional[ActiveNote]:
        if note_id in self.active_notes:
            return self.active_notes[note_id]

        try:
            # NECESSARY CHANGE: Pass 'self' (Service) to ActiveNote
            new_note = ActiveNote(note_id, self)
            self.active_notes[note_id] = new_note
            return new_note
        except Exception as e:
            sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Could not open note {note_id}", meta={"error": str(e)})
            return None

    def close_note(self, note_id: str):
        if note_id in self.active_notes:
            self.active_notes[note_id].close()
            del self.active_notes[note_id]
            sys_log.log(LogSource.SYSTEM, LogLevel.DEBUG, f"Closed note {note_id}")

# NECESSARY CHANGE: Removed global 'state_manager' instance