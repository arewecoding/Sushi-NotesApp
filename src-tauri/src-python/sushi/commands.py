"""
Sushi IPC Commands
===================
All PyTauri command handlers (IPC entry points from the frontend).
"""

from typing import Optional, List, Dict, Any

from pytauri import AppHandle, Commands, Manager

from sushi.vault_service import VaultService
from sushi.cache_db import NoteMetadata
from sushi.models import (
    OpenNoteRequest,
    CreateNoteRequest,
    CreateBlockRequest,
    UpdateBlockRequest,
    DeleteBlockRequest,
    UpdateNoteContentRequest,
    GetDirectoryRequest,
    OperationResponse,
    NoteListItem,
    NoteContent,
    DirectoryItem,
    DirectoryContents,
)
from sushi.logger import sys_log, LogSource, LogLevel


# ==========================================
# Commands Container (shared with __init__.py)
# ==========================================
commands: Commands = Commands()


# ==========================================
# Serialization Helpers
# ==========================================


def _snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def _dict_to_camel(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively converts dict keys from snake_case to camelCase."""
    result = {}
    for key, value in d.items():
        camel_key = _snake_to_camel(key)
        if isinstance(value, dict):
            result[camel_key] = _dict_to_camel(value)
        elif isinstance(value, list):
            result[camel_key] = [
                _dict_to_camel(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[camel_key] = value
    return result


# ==========================================
# Command Handlers
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
        target_path = body.dir_path if body.dir_path else str(vault_service.vault_path)
        contents = vault_service.db.get_directory_contents(target_path)

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
    """Returns a list of all notes for the sidebar navigation."""
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
    """Opens a note and returns its full content."""
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
            blocks=[_dict_to_camel(b.to_dict()) for b in active_note.note_obj.blocks],
        )
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"open_note failed: {e}")
        raise


@commands.command()
async def update_note_content(
    body: UpdateNoteContentRequest, app_handle: AppHandle
) -> OperationResponse:
    """Updates a note's content (title and blocks)."""
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
    """Creates a new note with the given title."""
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
    """Adds a new block to an open note."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)

        if not active_note:
            return OperationResponse(success=False, message="Note not open")

        active_note.add_block(body.block_type, **body.content_data)
        return OperationResponse(success=True, message="Block added")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"add_block failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def update_block(
    body: UpdateBlockRequest, app_handle: AppHandle
) -> OperationResponse:
    """Updates an existing block in an open note."""
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
    """Deletes a block from an open note."""
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
