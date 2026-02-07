"""
PyTauri Notes App Backend
=========================
This module integrates the Notes App backend with PyTauri IPC system.
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from anyio.from_thread import start_blocking_portal
from pydantic import BaseModel

from pytauri import (
    AppHandle,
    Commands,
    builder_factory,
    context_factory,
    Manager,
)

# --- Import Notes App modules ---
from sushi.active_state import VaultService
from sushi.cache_db import NoteMetadata
from sushi.ipc_models import (
    PyTauriModel,
    OpenNoteRequest,
    CreateBlockRequest,
    UpdateBlockRequest,
    DeleteBlockRequest,
    OperationResponse,
)
from sushi.logger_service import sys_log, LogSource, LogLevel


# ==========================================
# PyTauri Commands Container
# ==========================================
commands: Commands = Commands()


# Helper function to convert snake_case dict keys to camelCase
def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def dict_to_camel(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively converts all dict keys from snake_case to camelCase."""
    result = {}
    for key, value in d.items():
        camel_key = snake_to_camel(key)
        if isinstance(value, dict):
            result[camel_key] = dict_to_camel(value)
        elif isinstance(value, list):
            result[camel_key] = [
                dict_to_camel(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[camel_key] = value
    return result


# ==========================================
# Request/Response Models for Commands
# ==========================================


class CreateNoteRequest(PyTauriModel):
    title: str = "Untitled Note"


class NoteListItem(PyTauriModel):
    """Simplified note metadata for sidebar display."""

    note_id: str
    note_title: str


class NoteContent(PyTauriModel):
    """Full note content returned to frontend."""

    note_id: str
    title: str
    blocks: List[Dict[str, Any]]


class UpdateNoteContentRequest(PyTauriModel):
    """Request to update a note's content (title and blocks)."""

    note_id: str
    title: str
    blocks: List[Dict[str, Any]]


class GetDirectoryRequest(PyTauriModel):
    """Request to get directory contents. Empty path means vault root."""

    dir_path: Optional[str] = None


class DirectoryItem(PyTauriModel):
    """A directory in the file tree."""

    dir_path: str
    dir_name: str


class DirectoryContents(PyTauriModel):
    """Contents of a directory - subdirs and notes."""

    subdirs: List[DirectoryItem]
    notes: List[NoteListItem]


# ==========================================
# PyTauri Commands (IPC Handlers)
# ==========================================


@commands.command()
async def get_directory_contents(
    body: GetDirectoryRequest, app_handle: AppHandle
) -> DirectoryContents:
    """
    Returns the contents of a directory (subdirs and notes).
    If dir_path is None or empty, returns contents of the vault root.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)

        # Use vault root if no path specified
        target_path = body.dir_path if body.dir_path else str(vault_service.vault_path)

        # Get contents from the database
        contents = vault_service.db.get_directory_contents(target_path)

        # Convert to response models
        subdirs = [
            DirectoryItem(dir_path=d["dir_path"], dir_name=d["dir_name"])
            for d in contents["subdirs"]
        ]
        notes = [
            NoteListItem(note_id=n["note_id"], note_title=n["note_title"])
            for n in contents["notes"]
        ]

        sys_log.log(
            LogSource.API,
            LogLevel.DEBUG,
            f"get_directory_contents: {len(subdirs)} dirs, {len(notes)} notes in {target_path}",
        )

        return DirectoryContents(subdirs=subdirs, notes=notes)
    except Exception as e:
        sys_log.log(
            LogSource.API, LogLevel.ERROR, f"get_directory_contents failed: {e}"
        )
        raise


@commands.command()
async def get_sidebar(app_handle: AppHandle) -> List[NoteListItem]:
    """
    Returns a list of all notes for the sidebar navigation.
    This is equivalent to calling vault_service.get_sidebar_data()
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        all_notes: List[NoteMetadata] = vault_service.get_sidebar_data()

        return [
            NoteListItem(note_id=n.note_id, note_title=n.note_title) for n in all_notes
        ]
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"get_sidebar failed: {e}")
        raise


@commands.command()
async def open_note(
    body: OpenNoteRequest, app_handle: AppHandle
) -> Optional[NoteContent]:
    """
    Opens a note and returns its full content.
    The note is loaded into memory for editing.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note or not active_note.note_obj:
            sys_log.log(
                LogSource.API, LogLevel.ERROR, f"Note not found: {body.note_id}"
            )
            return None

        return NoteContent(
            note_id=active_note.note_id,
            title=active_note.note_obj.metadata.title,
            blocks=[dict_to_camel(b.to_dict()) for b in active_note.note_obj.blocks],
        )
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"open_note failed: {e}")
        raise


@commands.command()
async def update_note_content(
    body: UpdateNoteContentRequest, app_handle: AppHandle
) -> OperationResponse:
    """
    Updates a note's content (title and blocks).
    Called when the user edits and saves the note.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note:
            return OperationResponse(success=False, message="Note not open")

        success = active_note.update_content(body.title, body.blocks)
        if success:
            return OperationResponse(success=True, message="Note content updated")
        return OperationResponse(success=False, message="Failed to update note")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"update_note_content failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def create_note(
    body: CreateNoteRequest, app_handle: AppHandle
) -> Optional[NoteListItem]:
    """
    Creates a new note with the given title.
    Returns the new note's metadata for sidebar update.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        meta = vault_service.create_note(body.title)

        if not meta:
            sys_log.log(
                LogSource.API, LogLevel.ERROR, f"Failed to create note: {body.title}"
            )
            return None

        return NoteListItem(note_id=meta.note_id, note_title=meta.note_title)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"create_note failed: {e}")
        raise


@commands.command()
async def add_block(
    body: CreateBlockRequest, app_handle: AppHandle
) -> OperationResponse:
    """
    Adds a new block to an open note.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note:
            return OperationResponse(success=False, message="Note not open")

        # Extract kwargs from content_data
        active_note.add_block(body.block_type, **body.content_data)
        return OperationResponse(success=True, message="Block added")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"add_block failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def update_block(
    body: UpdateBlockRequest, app_handle: AppHandle
) -> OperationResponse:
    """
    Updates an existing block in an open note.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note:
            return OperationResponse(success=False, message="Note not open")

        active_note.update_block(body.block_id, body.new_data)
        return OperationResponse(success=True, message="Block updated")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"update_block failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def delete_block(
    body: DeleteBlockRequest, app_handle: AppHandle
) -> OperationResponse:
    """
    Deletes a block from an open note.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note:
            return OperationResponse(success=False, message="Note not open")

        active_note.delete_block(body.block_id)
        return OperationResponse(success=True, message="Block deleted")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"delete_block failed: {e}")
        return OperationResponse(success=False, message=str(e))


# ==========================================
# PyTauri App Lifecycle
# ==========================================

# Hardcoded vault path for now - can be made configurable later
VAULT_PATH = Path("C:/Users/ADMIN/Development/PyTauri/project sushi sandbox-vault/")


def setup(app_handle: AppHandle) -> None:
    """
    Setup callback to initialize VaultService during app startup.
    This is called by PyTauri before the app window opens.
    """
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, f"Setting up VaultService at: {VAULT_PATH}"
    )

    # Ensure vault directory exists
    if not VAULT_PATH.exists():
        try:
            VAULT_PATH.mkdir(parents=True, exist_ok=True)
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"Created vault directory: {VAULT_PATH}",
            )
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Failed to create vault: {e}"
            )
            raise

    # Initialize and register VaultService as managed state
    vault_service = VaultService(VAULT_PATH, app_handle)
    vault_service.start()

    Manager.manage(app_handle, vault_service)
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, "VaultService registered as managed state"
    )


def main() -> int:
    """PyTauri application entry point."""
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(
            context=context_factory(),
            invoke_handler=commands.generate_handler(portal),
            setup=setup,
        )
        exit_code = app.run_return()
        return exit_code
