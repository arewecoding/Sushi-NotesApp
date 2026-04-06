"""
Sushi Vault Service
====================
Core application state: VaultService (the brain), ActiveNote (open note state),
and ActiveFileTree (navigation state).
"""

import threading
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Union, Any

from pytauri import AppHandle

from sushi.cache_db import FileIndex, NoteMetadata
from sushi.filesys import atomic_write
from sushi.resource_manager import ResourceManager
from sushi.watcher import VaultWatcher
from sushi.filesys import (
    update_note,
    create_new_note,
    get_note_filepath,
    extract_short_id,
    delete_note as filesys_delete_note,
    delete_directory as filesys_delete_directory,
    create_directory as filesys_create_directory,
    move_item as filesys_move_item,
    duplicate_note as filesys_duplicate_note,
    rename_note as filesys_rename_note,
    rename_directory as filesys_rename_directory,
)
from sushi.migrations import migrate_canvas
try:
    from send2trash import send2trash
except ImportError:
    send2trash = None
from sushi.logger import sys_log, LogSource, LogLevel
from sushi.note_schema import JNote, NoteBlock
from sushi.block_factory import UnifiedBlockFactory
from sushi.models import (
    TreeChangedPayload,
    NoteContentChangedPayload,
    NoteDeletedPayload,
)

# PyTauri imports (type hints + optional runtime)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytauri import AppHandle

try:
    from pytauri import Emitter, AppHandle as AppHandleType

    HAS_EMITTER = True
except ImportError:
    HAS_EMITTER = False
    AppHandleType = None


# How long (seconds) a saved note is shielded from watcher-driven hot-swaps.
# Must exceed the worst-case watchdog debounce + Windows NTFS event delay.
# 5 seconds covers even high-load machines where the observer thread is starved.
ECHO_SUPPRESSION_TTL_SEC: float = 5.0


# ==========================================
# Active File Tree (Navigation State)
# ==========================================


class ActiveFileTree:
    """
    Manages the navigation sidebar state.
    Listens for structural changes (created/deleted/moved) and signals
    the frontend to refresh via Tauri events.
    """

    def __init__(self, app_handle: Optional["AppHandle"] = None):
        self.needs_refresh = False
        self._app_handle = app_handle

    def set_app_handle(self, app_handle: "AppHandle"):
        """Set AppHandle for event emission (called after VaultService is registered)."""
        self._app_handle = app_handle

    def handle_structure_change(self, path: str, event_type: str = "modified"):
        """
        Called when a file/directory is created, moved, or deleted.
        Emits a tree-changed event to the frontend.
        """
        self.needs_refresh = True
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            f"File tree changed: {path} ({event_type})",
        )

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
# Active Note (Memory State)
# ==========================================


class ActiveNote:
    """
    Represents a single open note in memory.
    Uses strict JNote objects and the filesys module for I/O.
    Implements 'Echo Suppression' to handle local vs external edits.
    """

    def __init__(self, note_id: str, service: "VaultService"):
        self.note_id = note_id
        self.service = service
        self.note_obj: Optional[JNote] = None
        self.is_dirty = False

        # Echo Suppression: when we save, record the expected mtime.
        # If a watcher event arrives with that exact mtime, we ignore it.
        self._last_save_mtime: Optional[float] = None

        # Auto-save timer
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._SAVE_DELAY = 2.5  # seconds

        # Load the note immediately
        self._load_from_disk()

        sys_log.log(
            LogSource.SYSTEM, LogLevel.INFO, f"ActiveNote created for: {note_id}"
        )

    # ==========================================
    # Loading
    # ==========================================

    def _load_from_disk(self):
        """Initial blocking load from disk."""
        meta = self.service.db.get_metadata(self.note_id)
        if not meta:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Cannot load note {self.note_id}: not found in DB",
            )
            return

        file_path = get_note_filepath(self.service.db, self.note_id)
        if not file_path:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Cannot derive filepath for note: {self.note_id}",
            )
            return
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

    def handle_external_update(self, event_mtime: float):
        """Called by VaultService when the watcher detects an external change."""
        # Suppress if this is our own save echoing back
        if self._last_save_mtime and abs(event_mtime - self._last_save_mtime) < 0.1:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.DEBUG, f"Suppressed echo for {self.note_id}"
            )
            return

        # External change — trigger a hot swap
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            f"External change detected for {self.note_id}",
        )
        self._trigger_hot_swap()

    def _trigger_hot_swap(self):
        """Reloads data in a background thread."""
        thread = threading.Thread(target=self._perform_hot_swap, daemon=True)
        thread.start()

    def _perform_hot_swap(self):
        meta = self.service.db.get_metadata(self.note_id)
        if not meta:
            return

        file_path = get_note_filepath(self.service.db, self.note_id)
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            new_note = JNote.from_dict(raw_data, str(file_path))

            if new_note:
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
    # Block Editing
    # ==========================================

    def add_block(self, block_type: str, **kwargs) -> Dict:
        """Uses UnifiedBlockFactory to append a new block."""
        if not self.note_obj:
            raise ValueError("Note not open")
            
        note_path = get_note_filepath(self.service.db, self.note_id)
        if not note_path:
            raise ValueError("Note path not found")
            
        block_dict = UnifiedBlockFactory.build_block(
            block_type=block_type,
            note_id=self.note_id,
            resource_manager=self.service.resource_manager,
            note_dir=note_path.parent,
            **kwargs
        )
        new_block = NoteBlock.from_dict(block_dict)
        self.note_obj.blocks.append(new_block)
        self.is_dirty = True
        self._schedule_save()
        return block_dict

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

    def update_content(self, title: str, blocks: list) -> bool:
        """
        Updates the entire note content (title and blocks).
        Called from frontend when user edits the note.
        """
        if not self.note_obj:
            return False

        self.note_obj.metadata.title = title
        self.note_obj.metadata.update_timestamp()

        # Convert from dict list to NoteBlock objects (handles camelCase from frontend)
        new_blocks = []
        for block_dict in blocks:
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

        # Reconcile resource ownership: clean up files for removed blocks
        current_block_ids = {
            b.block_id for b in new_blocks if b.block_id
        }
        try:
            self.service.reconcile_block_resources(self.note_id, current_block_ids)
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.ERROR,
                f"Resource reconciliation failed: {e}",
            )

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

        # Guard: tell VaultService we're saving so watchdog events are suppressed
        self.service.mark_saving(self.note_id)
        try:
            new_mtime = update_note(self.service.db, self.note_obj)
            if new_mtime:
                self._last_save_mtime = new_mtime
                self.is_dirty = False
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"Auto-saved: {self.note_obj.metadata.title}",
                )
        finally:
            self.service.unmark_saving(self.note_id)

    def close(self, skip_save: bool = False):
        """Cancel pending timers. Flush save unless skip_save (e.g. file was deleted)."""
        if self._save_timer:
            self._save_timer.cancel()
        if self.is_dirty and not skip_save:
            self._save_to_disk()


# ==========================================
# Vault Service (The Brain)
# ==========================================


class VaultService:
    """
    The single source of truth for the application.
    Holds the Database, the File Watcher, and all Active Notes.
    """

    def __init__(
        self, vault_path: Union[str, Path], app_handle: Optional["AppHandle"] = None
    ):
        self.vault_path = Path(vault_path)
        self._app_handle = app_handle

        # Core components
        self.db = FileIndex()
        self.watcher = VaultWatcher(self.vault_path, self.db, self.on_file_event)
        self.file_tree = ActiveFileTree(app_handle)
        self.resource_manager = ResourceManager(self.db, self.vault_path)

        # Active notes registry
        self._active_notes: Dict[str, ActiveNote] = {}

        # Guard: tracks note_ids currently being saved and when their suppression expires.
        # Maps note_id -> monotonic expiry time (time.monotonic() + ECHO_SUPPRESSION_TTL_SEC).
        # NOT cleared immediately after the write — the entry lives until TTL expires so
        # that delayed watchdog events are still caught and suppressed.
        self._saving_note_ids: Dict[str, float] = {}

        # Guard: canvas paths currently being renamed/deleted by the app.
        # Maps absolute path str -> monotonic expiry time.
        # Suppresses spurious watcher tree-changed events for our own renames/deletes.
        self._suppressed_canvas_paths: Dict[str, float] = {}

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            f"VaultService initialized for: {self.vault_path}",
        )

    def set_app_handle(self, app_handle: "AppHandle"):
        """Update AppHandle for event emission after registration."""
        self._app_handle = app_handle
        self.file_tree.set_app_handle(app_handle)

    def start(self):
        """Starts initial scan and file watching."""
        self.watcher.scan(self.db)
        self.resource_manager.scan_vault_incremental()
        self.watcher.start()
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "VaultService started.")

    def mark_saving(self, note_id: str) -> None:
        """Register note_id as recently saved. Suppresses watcher events for TTL seconds."""
        self._saving_note_ids[note_id] = time.monotonic() + ECHO_SUPPRESSION_TTL_SEC

    def unmark_saving(self, note_id: str) -> None:
        """No-op: the TTL entry expires naturally. Called for API symmetry."""
        # Intentionally NOT removing the entry here.
        # The watcher event from watchdog can arrive seconds after the write on Windows;
        # if we remove the suppression immediately after atomic_write completes, we leave
        # a window where the delayed event passes through and triggers a hot-swap.
        # Entries are consumed on first matched event or expire after ECHO_SUPPRESSION_TTL_SEC.

    def suppress_canvas_path(self, path: str) -> None:
        """Suppress watcher tree-changed events for a canvas path for TTL seconds."""
        self._suppressed_canvas_paths[path] = time.monotonic() + ECHO_SUPPRESSION_TTL_SEC

    def _is_canvas_path_suppressed(self, path: str) -> bool:
        """Return True if the canvas path is within its suppression TTL window."""
        expiry = self._suppressed_canvas_paths.get(path)
        if expiry is None:
            return False
        if time.monotonic() < expiry:
            return True
        # TTL expired
        del self._suppressed_canvas_paths[path]
        return False

    def stop(self):
        """Stops file watching and closes all active notes."""
        self.watcher.stop()
        for note_id in list(self._active_notes.keys()):
            self.close_note(note_id)
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "VaultService stopped.")

    # ==========================================
    # File Event Callback (from Watcher)
    # ==========================================

    def on_file_event(self, path_str: str, mtime: float):
        """Callback triggered by VaultWatcher for every file event."""
        path = Path(path_str)

        # Ignore all writes inside resource directories
        if ".sushi-resources" in path.parts:
            sys_log.log(LogSource.SYSTEM, LogLevel.DEBUG, f"Resource write ignored: {path_str}")
            return

        # Determine event type from mtime
        if mtime == 0.0:
            event_type = "deleted"
        elif mtime == -1.0:
            event_type = "moved"
        elif path.exists():
            event_type = "modified"
        else:
            event_type = "created"

        # Directory or non-.jnote → update file tree unless canvas-path is suppressed.
        if path.is_dir() or path.suffix != ".jnote":
            if not self._is_canvas_path_suppressed(path_str):
                self.file_tree.handle_structure_change(path_str, event_type)
            else:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.DEBUG,
                    f"Canvas path suppressed: {path_str}",
                )
            return

        # --- Note file event handling ---
        is_echo = False
        note_id = None
        short_id = extract_short_id(path.name)

        if short_id:
            # Try DB lookup first (works for create/modify/move)
            matches = self.db.get_metadata_by_short_id(short_id, str(path.parent))
            if len(matches) == 1:
                note_id = matches[0].note_id

            # For delete events, the watcher already removed the DB entry
            # before calling us, so fall back to matching active notes by short_id
            if note_id is None and event_type == "deleted":
                for nid in self._active_notes:
                    if nid.startswith(short_id):
                        note_id = nid
                        break

            # Echo suppression check — TTL dict; entry is kept until expiry so
            # secondary writes (e.g. _resolve_identity's last_known_path stamp)
            # that generate additional watcher events are also covered.
            if note_id and note_id in self._active_notes:
                active_note = self._active_notes[note_id]
                expiry = self._saving_note_ids.get(note_id)
                if expiry is not None:
                    if time.monotonic() < expiry:
                        # Within TTL — suppress this event; keep entry for subsequent events.
                        sys_log.log(
                            LogSource.SYSTEM,
                            LogLevel.DEBUG,
                            f"Echo suppressed (TTL) for {note_id}",
                        )
                        is_echo = True
                    else:
                        # TTL has expired — stale entry, clean up.
                        del self._saving_note_ids[note_id]
                elif (
                    active_note._last_save_mtime
                    and abs(mtime - active_note._last_save_mtime) < 2.0
                ):
                    # Secondary guard: mtime very close to our last write.
                    # Tolerance widened to 2.0 s to cover filesystem clock granularity.
                    is_echo = True

        if is_echo:
            return  # Self-save echo — skip everything

        # Structural changes update the tree; content mods do not
        if event_type in ("created", "deleted", "moved"):
            self.file_tree.handle_structure_change(path_str, event_type)

        # Handle deletion of an active note — close it and notify frontend
        if event_type == "deleted" and note_id and note_id in self._active_notes:
            # skip_save=True because the file no longer exists on disk
            self.close_note(note_id, skip_save=True)
            if HAS_EMITTER and self._app_handle is not None:
                try:
                    Emitter.emit(
                        self._app_handle,
                        "note-deleted",
                        NoteDeletedPayload(note_id=note_id),
                    )
                    sys_log.log(
                        LogSource.SYSTEM,
                        LogLevel.INFO,
                        f"Emitted note-deleted for {note_id}",
                    )
                except Exception as e:
                    sys_log.log(
                        LogSource.SYSTEM,
                        LogLevel.ERROR,
                        f"Failed to emit note-deleted: {e}",
                    )
            return

        # Notify ActiveNote of genuine external content changes only
        if (
            event_type == "modified"
            and note_id
            and note_id in self._active_notes
        ):
            self._active_notes[note_id].handle_external_update(mtime)

    # ==========================================
    # Note Operations (Business Logic)
    # ==========================================

    def get_sidebar_data(self):
        """Fetch all notes from the DB for sidebar display."""
        return self.db.get_all_notes()

    def create_note(self, title: str) -> Optional[NoteMetadata]:
        """Creates a note on disk and registers it in the DB immediately."""
        note = create_new_note(str(self.vault_path), title)
        if not note:
            return None

        meta = NoteMetadata(
            note_id=note.metadata.note_id,
            note_title=note.metadata.title,
            note_version=note.metadata.version,
            note_dir=self.vault_path,
        )
        # Register in DB immediately so get_directory_contents returns it
        # (watcher's INSERT OR REPLACE is idempotent — safe double-write)
        self.db.add_metadata(meta)
        return meta

    def get_or_open_note(self, note_id: str) -> Optional[ActiveNote]:
        """Return an existing ActiveNote or open a new one."""
        if note_id in self._active_notes:
            return self._active_notes[note_id]

        active_note = ActiveNote(note_id, self)
        if active_note.note_obj:
            self._active_notes[note_id] = active_note
            return active_note
        return None

    def close_note(self, note_id: str, skip_save: bool = False):
        """Close an active note. skip_save=True when file was externally deleted."""
        if note_id in self._active_notes:
            self._active_notes[note_id].close(skip_save=skip_save)
            del self._active_notes[note_id]
            sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Closed note: {note_id}")

    # ==========================================
    # File Tree CRUD Operations
    # ==========================================

    def create_note_in_dir(self, title: str, dir_path: str) -> Optional[NoteMetadata]:
        """Creates a note in a specific directory and registers it in the DB immediately."""
        note = create_new_note(dir_path, title)
        if not note:
            return None
        meta = NoteMetadata(
            note_id=note.metadata.note_id,
            note_title=note.metadata.title,
            note_version=note.metadata.version,
            note_dir=Path(dir_path),
        )
        self.db.add_metadata(meta)
        return meta

    def delete_note_by_id(self, note_id: str) -> bool:
        """Closes active note (if open), deletes tracked resources, and deletes the note from disk."""
        self.close_note(note_id, skip_save=True)

        # Clean up all tracked resource files before deleting the note
        self._delete_note_resources(note_id)

        return filesys_delete_note(self.db, note_id)

    def delete_directory_by_path(self, dir_path: str) -> bool:
        """Closes any active notes inside, then deletes directory."""
        # Close all active notes whose files are in this directory
        notes_to_close = []
        dir_p = Path(dir_path)
        for nid, an in self._active_notes.items():
            if an.note_obj:
                fp = get_note_filepath(self.db, nid)
                if fp and str(fp).startswith(str(dir_p)):
                    notes_to_close.append(nid)
        for nid in notes_to_close:
            self.close_note(nid, skip_save=True)

        return filesys_delete_directory(dir_path)

    def _resolve_dest_dir(self, dest_dir: str) -> str:
        """If dest_dir is empty, resolve to vault root."""
        if not dest_dir or not dest_dir.strip():
            return str(self.vault_path)
        return dest_dir

    def move_item(self, src_path: str, dest_dir: str) -> tuple[bool, str]:
        """Moves a file or directory. Returns (success, message). Watcher handles DB updates."""
        dest_dir = self._resolve_dest_dir(dest_dir)
        result, message = filesys_move_item(src_path, dest_dir)
        if result is not None:
            return True, "Item moved"
        return False, message

    def move_note_by_id(self, note_id: str, dest_dir: str) -> bool:
        """Moves a note by ID — resolves path from DB first."""
        dest_dir = self._resolve_dest_dir(dest_dir)
        self.close_note(note_id, skip_save=False)
        file_path = get_note_filepath(self.db, note_id)
        if not file_path:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Note not found for move: {note_id}"
            )
            return False
        result = filesys_move_item(str(file_path), dest_dir)
        return result is not None

    def rename_note_by_id(self, note_id: str, new_title: str) -> bool:
        """Renames a note — closes it first, then updates title and filename."""
        self.close_note(note_id, skip_save=False)
        return filesys_rename_note(self.db, note_id, new_title)

    def rename_directory_by_path(self, dir_path: str, new_name: str) -> bool:
        """Renames a directory on disk. Watcher handles DB updates."""
        # Close any active notes inside this directory
        dir_p = Path(dir_path)
        notes_to_close = []
        for nid, an in self._active_notes.items():
            if an.note_obj:
                fp = get_note_filepath(self.db, nid)
                if fp and str(fp).startswith(str(dir_p)):
                    notes_to_close.append(nid)
        for nid in notes_to_close:
            self.close_note(nid, skip_save=False)
        result = filesys_rename_directory(dir_path, new_name)
        return result is not None

    def duplicate_note_by_id(self, note_id: str) -> Optional[NoteMetadata]:
        """Duplicates a note and registers the copy in the DB immediately."""
        copy = filesys_duplicate_note(self.db, note_id)
        if not copy:
            return None
        # Get the actual directory from the original note
        original_meta = self.db.get_metadata(note_id)
        note_dir = original_meta.note_dir if original_meta else self.vault_path
        meta = NoteMetadata(
            note_id=copy.metadata.note_id,
            note_title=copy.metadata.title,
            note_version=copy.metadata.version,
            note_dir=note_dir,
        )
        self.db.add_metadata(meta)
        return meta

    def create_directory_in(self, parent_path: str, dir_name: str) -> bool:
        """Creates a subdirectory. Watcher triggers tree refresh."""
        # Empty parent_path means vault root — Path("") would resolve to CWD
        resolved_parent = parent_path if parent_path else str(self.vault_path)
        result = filesys_create_directory(resolved_parent, dir_name)
        return result is not None

    # ==========================================
    # Canvas File Operations
    # ==========================================

    def create_canvas_file(self, title: str, directory: str) -> dict:
        directory = self._resolve_dest_dir(directory)
        file_id = str(uuid.uuid4())
        
        # Simple slugification
        slug = "".join(c if c.isalnum() else "-" for c in title).strip("-").lower()
        slug = "-".join(filter(None, slug.split("-")))
        if not slug:
            slug = "canvas"
        
        filename = f"{slug}-{file_id[:8]}.jcanvas"
        full_path = Path(directory) / filename
        
        now = datetime.now(timezone.utc).isoformat()
        
        canvas_data = {
            "metadata": {
                "file_id": file_id,
                "title": title,
                "created_at": now,
                "last_modified": now,
                "version": "1.0",
                "mode": "canvas"
            },
            "background": {
                "type": "none",
                "color": "#d0d0d0",
                "spacing": 20,
                "tile_ref": None
            },
            "viewport": {
                "offset_x": 0.0,
                "offset_y": 0.0,
                "scale": 1.0
            },
            "strokes": [],
            "text_objects": [],
            "image_objects": [],
            "resources": {}
        }
        
        # Write to disk
        atomic_write(full_path, json.dumps(canvas_data, indent=2))
        
        # Update db
        cursor = self.db.conn.cursor()
        file_dir = str(full_path.parent)
        full_path_str = str(full_path)
        cursor.execute(
            """
            INSERT OR REPLACE INTO canvas_files 
            (file_id, title, path, file_type, file_dir, created_at, last_modified, last_known_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, title, full_path_str, "jcanvas", file_dir, now, now, full_path_str)
        )
        self.db.conn.commit()
        
        # Emit tree change
        self.file_tree.handle_structure_change(full_path_str, "created")
        
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Created canvas: {file_id}")
        return {"file_id": file_id, "path": full_path_str}

    def open_canvas_file(self, path: str) -> dict:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Canvas not found: {path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return migrate_canvas(data)

    def save_canvas_file(self, file_id: str, path: str, canvas_data: dict) -> None:
        file_path = Path(path)
        now = datetime.now(timezone.utc).isoformat()
        
        if "metadata" not in canvas_data:
            canvas_data["metadata"] = {}
        canvas_data["metadata"]["last_modified"] = now
        
        atomic_write(file_path, json.dumps(canvas_data, indent=2))
        
        cursor = self.db.conn.cursor()
        cursor.execute(
            "UPDATE canvas_files SET last_modified = ? WHERE file_id = ?",
            (now, file_id)
        )
        self.db.conn.commit()
        
        sys_log.log(LogSource.SYSTEM, LogLevel.DEBUG, f"Saved canvas: {file_id}")

    def save_canvas_block(
        self,
        note_id: str,
        block_id: str,
        canvas_ref: str,
        canvas_data: dict,
        thumbnail_data_url: Optional[str] = None,
    ) -> Optional[str]:
        """Persist an embedded canvas block and its thumbnail inside the note's resources dir.
        
        If thumbnail_data_url is omitted, the prior thumbnail on disk (if any) is preserved.

        Args:
            note_id: The owning note's UUID.
            block_id: The block's UUID within the note.
            canvas_ref: Filename of the canvas file, e.g. ``abc123.jcanvas``.
            canvas_data: Serialized canvas state from the WASM engine.
            thumbnail_data_url: Optional base64 PNG data URL to save as the thumbnail.

        Returns:
            The thumbnail filename (stem + "-thumb.png").

        Raises:
            FileNotFoundError: If the note's path cannot be resolved from the DB.
        """
        note_path = get_note_filepath(self.db, note_id)
        if not note_path:
            raise FileNotFoundError(f"Note path not found for note_id={note_id}")

        res_id = Path(canvas_ref).stem
        self.resource_manager.update_resource(res_id, canvas_data)

        thumb_filename = None
        if thumbnail_data_url:
            try:
                from sushi.resource_manager import ResourceNotFound
                thumb_res = self.resource_manager.get_resource(res_id + "-thumb", check_exists=False)
            except ResourceNotFound:
                thumb_res = self.resource_manager.create_resource(block_id, "thumbnail", note_path.parent, res_id=res_id)
            
            self.resource_manager.update_resource(thumb_res.resource_id, thumbnail_data_url)
            thumb_filename = thumb_res.file_path.name

        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.DEBUG,
            "canvas_block_saved",
            meta={
                "note_id": note_id,
                "block_id": block_id,
                "canvas_ref": canvas_ref,
            }
        )

        return thumb_filename

    def load_canvas_block(self, note_id: str, canvas_ref: str) -> Optional[dict]:
        """Load the stored canvas data for an embedded block.

        Args:
            note_id: The owning note's UUID.
            canvas_ref: Filename of the canvas file, e.g. ``abc123.jcanvas``.

        Returns:
            Migrated canvas dict, or None if the file does not exist yet
            (new block that has never been saved).

        Raises:
            FileNotFoundError: If the note's path cannot be resolved from the DB.
        """
        res_id = Path(canvas_ref).stem
        try:
            resource = self.resource_manager.get_resource(res_id, check_exists=True)
            if not resource.exists():
                return None
            data = json.loads(resource.read().decode("utf-8"))
            return migrate_canvas(data)
        except Exception as e:
            sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, f"Failed to load canvas: {e}")
            return None

    def delete_canvas_file(self, file_id: str, path: str) -> None:
        file_path = Path(path)
        
        if file_path.exists():
            if send2trash:
                try:
                    send2trash(str(file_path))
                except Exception:
                    os.remove(file_path)
            else:
                os.remove(file_path)
                
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM canvas_files WHERE file_id = ?", (file_id,))
        self.db.conn.commit()
        
        self.file_tree.handle_structure_change(str(file_path), "deleted")
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, f"Deleted canvas: {file_id}")

    def rename_canvas_file(self, file_id: str, old_path: str, new_name: str) -> str:
        """Rename a .jcanvas/.jbook file, preserving its original extension.

        Args:
            file_id: stable UUID of the canvas file.
            old_path: current absolute path of the file.
            new_name: desired filename stem (extension auto-preserved).

        Returns:
            The new absolute path as a string.

        Raises:
            FileNotFoundError: if old_path does not exist.
            FileExistsError: if a file with the new name already exists.
        """
        old = Path(old_path)
        if not old.exists():
            raise FileNotFoundError(f"Canvas file not found: {old_path}")

        # Preserve the original extension (.jcanvas or .jbook)
        extension = old.suffix
        new_filename = new_name if new_name.endswith(extension) else new_name + extension
        new_path = old.parent / new_filename

        if new_path.exists():
            raise FileExistsError(f"A file named '{new_filename}' already exists")

        # Suppress watcher events for both old and new paths before the rename.
        # The watchdog MovedEvent (or delete+create pair) arrives after the OS rename;
        # without suppression it would emit a tree-changed and cause a ghost duplicate.
        self.suppress_canvas_path(str(old))
        self.suppress_canvas_path(str(new_path))

        old.rename(new_path)

        cursor = self.db.conn.cursor()
        cursor.execute(
            "UPDATE canvas_files SET path = ?, last_known_path = ? WHERE file_id = ?",
            (str(new_path), str(new_path), file_id),
        )
        self.db.conn.commit()

        # Emit exactly one tree-changed ourselves (suppression blocks the watcher duplicate).
        self.file_tree.handle_structure_change(str(new_path), "moved")
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            f"Renamed canvas: {file_id}",
            meta={
                "old": old_path,
                "new": str(new_path),
            }
        )
        return str(new_path)

    # ==========================================
    # Resource Garbage Collection
    # ==========================================

    def _delete_note_resources(self, note_id: str):
        """Delete all tracked resource files for a note from disk and the DB.

        Called before a note is permanently deleted. Silently skips files
        that have already been removed externally.
        """
        note_path = get_note_filepath(self.db, note_id)
        if not note_path:
            return


        # We don't have block IDs here, so we just delete the .sushi-resources dir
        # if it exists, assuming this note was the only one using it, or wait for garbage collection.
        # However, to be safe since it's shared, we will NOT delete the folder automatically.
        sys_log.log(
            LogSource.SYSTEM,
            LogLevel.INFO,
            "note_deleted_resource_cleanup_deferred",
            meta={"note_id": note_id},
        )

    def reconcile_block_resources(self, note_id: str, current_block_ids: set):
        """Remove resources for blocks that no longer exist in the note.

        Compares the set of block IDs currently in the note against the
        resource registry. Any DB entry whose block_id is not in the set
        gets its files deleted from disk and its records purged.

        Args:
            note_id: The note being reconciled.
            current_block_ids: Set of block_id strings still present in the note.
        """
        # Since we use `.jnote` as source of truth and incremental scanning, 
        # true orphan cleanup (deleting physical files) should be handled by a periodic garbage collector.
        # For now, we update the in-memory registry by re-scanning this note.
        note_path = get_note_filepath(self.db, note_id)
        if note_path:
            self.resource_manager._index_note_resources(note_path, note_id)
