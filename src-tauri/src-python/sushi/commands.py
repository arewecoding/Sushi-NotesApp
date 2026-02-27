"""
Sushi IPC Commands
===================
All PyTauri command handlers (IPC entry points from the frontend).
"""

import asyncio
from typing import Optional, List, Dict, Any

from pytauri import AppHandle, Commands, Manager

from sushi.vault_service import VaultService
from sushi.rag_service import RAGService
from sushi.cache_db import NoteMetadata
from sushi.models import (
    OpenNoteRequest,
    CreateNoteRequest,
    CreateNoteInDirRequest,
    DeleteNoteRequest,
    DeleteDirectoryRequest,
    MoveItemRequest,
    MoveNoteRequest,
    DuplicateNoteRequest,
    CreateDirectoryRequest,
    RenameNoteRequest,
    RenameDirectoryRequest,
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
    RagQueryRequest,
    RagQueryResponse,
    RagBuildIndexRequest,
    RagBuildIndexResponse,
    RagStatusResponse,
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


# ==========================================
# File Tree CRUD Commands
# ==========================================


@commands.command()
async def create_note_in_dir(
    body: CreateNoteInDirRequest, app_handle: AppHandle
) -> Optional[NoteListItem]:
    """Creates a new note in a specific directory."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        meta = vault_service.create_note_in_dir(body.title, body.dir_path)
        if not meta:
            return None
        return NoteListItem(note_id=meta.note_id, note_title=meta.note_title)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"create_note_in_dir failed: {e}")
        raise


@commands.command()
async def delete_note_cmd(
    body: DeleteNoteRequest, app_handle: AppHandle
) -> OperationResponse:
    """Deletes a note (closes if active, then removes file)."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.delete_note_by_id(body.note_id)
        if success:
            return OperationResponse(success=True, message="Note deleted")
        return OperationResponse(success=False, message="Note not found")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"delete_note_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def delete_directory_cmd(
    body: DeleteDirectoryRequest, app_handle: AppHandle
) -> OperationResponse:
    """Deletes a directory and all its contents."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.delete_directory_by_path(body.dir_path)
        if success:
            return OperationResponse(success=True, message="Directory deleted")
        return OperationResponse(success=False, message="Directory not found")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"delete_directory_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def move_item_cmd(
    body: MoveItemRequest, app_handle: AppHandle
) -> OperationResponse:
    """Moves a note or directory to another directory."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success, message = vault_service.move_item(body.source_path, body.dest_dir)
        return OperationResponse(success=success, message=message)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"move_item_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def duplicate_note_cmd(
    body: DuplicateNoteRequest, app_handle: AppHandle
) -> Optional[NoteListItem]:
    """Creates an exact copy of a note with 'Copy of' prefix."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        meta = vault_service.duplicate_note_by_id(body.note_id)
        if not meta:
            return None
        return NoteListItem(note_id=meta.note_id, note_title=meta.note_title)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"duplicate_note_cmd failed: {e}")
        raise


@commands.command()
async def create_directory_cmd(
    body: CreateDirectoryRequest, app_handle: AppHandle
) -> OperationResponse:
    """Creates a new subdirectory."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.create_directory_in(body.parent_path, body.dir_name)
        if success:
            return OperationResponse(success=True, message="Directory created")
        return OperationResponse(success=False, message="Failed to create directory")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"create_directory_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def move_note_cmd(
    body: MoveNoteRequest, app_handle: AppHandle
) -> OperationResponse:
    """Moves a note by ID to a destination directory."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.move_note_by_id(body.note_id, body.dest_dir)
        if success:
            return OperationResponse(success=True, message="Note moved")
        return OperationResponse(success=False, message="Move failed")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"move_note_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def rename_note_cmd(
    body: RenameNoteRequest, app_handle: AppHandle
) -> OperationResponse:
    """Renames a note by ID."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.rename_note_by_id(body.note_id, body.new_title)
        if success:
            return OperationResponse(success=True, message="Note renamed")
        return OperationResponse(success=False, message="Rename failed")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"rename_note_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


@commands.command()
async def rename_directory_cmd(
    body: RenameDirectoryRequest, app_handle: AppHandle
) -> OperationResponse:
    """Renames a directory."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        success = vault_service.rename_directory_by_path(body.dir_path, body.new_name)
        if success:
            return OperationResponse(success=True, message="Directory renamed")
        return OperationResponse(success=False, message="Rename failed")
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"rename_directory_cmd failed: {e}")
        return OperationResponse(success=False, message=str(e))


# ==========================================
# RAG Commands
# ==========================================


@commands.command()
async def rag_query(body: RagQueryRequest, app_handle: AppHandle) -> RagQueryResponse:
    """
    Run the full GraphRAG pipeline for a natural-language query.

    Executes in a background thread (asyncio.to_thread) so the Gemini API
    calls do not block the async event loop.
    """
    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        result = await asyncio.to_thread(rag_service.query, body.query)
        sys_log.log(
            LogSource.API,
            LogLevel.DEBUG,
            f"rag_query: strategy={result.get('strategy')} "
            f"blocks={result.get('blocks_retrieved')}",
        )
        return RagQueryResponse(**result)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"rag_query failed: {e}")
        return RagQueryResponse(
            answer=f"Query failed: {e}",
            strategy="error",
            query_original=body.query,
            query_optimized=body.query,
            blocks_retrieved=0,
            blocks_reranked=0,
            blocks_in_context=0,
            context_truncated=False,
            latency={},
            rag_enabled=False,
        )


@commands.command()
async def rag_build_index(
    body: RagBuildIndexRequest, app_handle: AppHandle
) -> RagBuildIndexResponse:
    """
    Trigger a full rebuild of the RAG index over the entire vault.

    This calls the Gemini embedding API for every block in the vault — it may
    take from a few seconds to a few minutes depending on vault size.
    Runs in a background thread so the UI stays responsive.
    """
    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        result = await asyncio.to_thread(rag_service.build_index)
        sys_log.log(
            LogSource.API,
            LogLevel.INFO,
            f"rag_build_index: {result}",
        )
        return RagBuildIndexResponse(**result)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"rag_build_index failed: {e}")
        return RagBuildIndexResponse(
            status="error",
            notes_indexed=0,
            blocks_indexed=0,
            graph_nodes=0,
            graph_edges=0,
            rag_enabled=False,
            message=str(e),
        )


@commands.command()
async def rag_status(app_handle: AppHandle) -> RagStatusResponse:
    """
    Return a health snapshot of the RAG index (fast, no API calls).

    Useful for the frontend to show whether RAG is available and how many
    notes are indexed.
    """
    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        result = rag_service.status()
        return RagStatusResponse(**result)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"rag_status failed: {e}")
        return RagStatusResponse(
            rag_enabled=False,
            faiss_vectors=0,
            tombstone_ratio=0.0,
            graph_nodes=0,
            graph_edges=0,
            message=str(e),
        )
