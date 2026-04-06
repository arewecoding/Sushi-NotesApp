"""
Sushi IPC Commands
===================
All PyTauri command handlers (IPC entry points from the frontend).
"""

import asyncio
from typing import Optional, List, Dict, Any

import structlog
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
    CanvasFileItem,
    RagQueryRequest,
    RagQueryResponse,
    RagBuildIndexRequest,
    RagBuildIndexResponse,
    RagStatusResponse,
    SearchRequest,
    SearchResultItem,
    SearchResponse,
    AppSettings,
    SaveSettingsRequest,
    SaveSettingsResponse,
    LogErrorPayload,
    FrontendLogPayload,
    ok,
    err,
    SAVE_FAILED,
    CANVAS_NOT_FOUND,
    LOAD_FAILED,
    NOTE_NOT_FOUND,
    CreateCanvasFileRequest,
    OpenCanvasFileRequest,
    SaveCanvasFileRequest,
    DeleteCanvasFileRequest,
    RenameCanvasFileRequest,
    GetResourcePathRequest,
    SaveCanvasBlockRequest,
    LoadCanvasBlockRequest,
)
from sushi.logger import sys_log, LogSource, LogLevel

log = structlog.get_logger(__name__)


# ==========================================
# Commands Container (shared with __init__.py)
# ==========================================
commands: Commands = Commands()


# ==========================================
# Client Error Logging Command
# ==========================================


@commands.command()
async def log_error_cmd(body: LogErrorPayload) -> dict:
    """Log errors reported by the frontend or WASM engine."""
    try:
        log.error(
            "client_error",
            log_source=body.source,
            message=body.message,
            stack=body.stack,
            timestamp=body.timestamp,
        )
        return ok({})
    except Exception as e:
        log.error("log_error_cmd_failed", error=str(e))
        return ok({})

@commands.command()
async def frontend_log_cmd(body: FrontendLogPayload) -> dict:
    """Logs coming from the Svelte frontend."""
    try:
        # We explicitly inject "SVELTE_UI" as the source and use the JS log level.
        # This will pipe directly into the python StructLog / logging infra.
        log_method = getattr(log, body.level if body.level in ['debug', 'info', 'warn', 'error'] else 'info', log.info)
        log_method(
            body.message, 
            log_source="SVELTE_UI", 
            js_timestamp=body.timestamp
        )
        return ok({})
    except Exception as e:
        log.error("frontend_log_cmd_failed", error=str(e))
        return ok({})


# ==========================================
# Serialization Helpers
# ==========================================


def _snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def _dict_to_camel(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively converts dict keys from snake_case to camelCase.
    Bypasses the 'data' key for Blocks to preserve verbatim schema."""
    result = {}
    for key, value in d.items():
        camel_key = _snake_to_camel(key)
        if key == "data" and isinstance(value, dict):
            # Preserve inner block data schemas verbatim
            result[camel_key] = value
        elif isinstance(value, dict):
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
        canvas_files = [
            CanvasFileItem(
                file_id=c["file_id"],
                title=c["title"],
                file_type=c["file_type"],
                file_path=c["path"],
            )
            for c in contents.get("canvas_files", [])
        ]

        sys_log.log(
            LogSource.API,
            LogLevel.DEBUG,
            f"get_directory_contents: {len(subdirs)} dirs, {len(notes)} notes, {len(canvas_files)} canvas in {target_path}",
        )

        return DirectoryContents(subdirs=subdirs, notes=notes, canvas_files=canvas_files)
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
async def create_block_cmd(
    body: CreateBlockRequest, app_handle: AppHandle
) -> Optional[dict]:
    """
    Generates a new block schema and provisions resources (like .jcanvas) if needed.
    Returns the initialized block dictionary to the frontend.
    """
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        active_note = vault_service.get_or_open_note(body.note_id)
        if not active_note:
            sys_log.log(LogSource.API, LogLevel.ERROR, f"Note not open: {body.note_id}")
            return None
            
        block_dict = active_note.add_block(body.block_type, **body.content_data)
        return _dict_to_camel(block_dict)
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"create_block_cmd failed: {e}")
        return None


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


# ==========================================
# Search Commands
# ==========================================


@commands.command()
async def search_fast(body: SearchRequest, app_handle: AppHandle) -> SearchResponse:
    """
    Tier 1 — fast keyword search (titles + FTS5 block content).
    No embedding API calls, sub-10ms.
    """
    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        results = rag_service.search_fast(body.query, body.limit)
        sys_log.log(
            LogSource.API,
            LogLevel.DEBUG,
            f"search_fast: query='{body.query}' results={len(results)}",
        )
        return SearchResponse(results=[SearchResultItem(**r) for r in results])
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"search_fast failed: {e}")
        return SearchResponse(results=[])


@commands.command()
async def search_deep(body: SearchRequest, app_handle: AppHandle) -> SearchResponse:
    """
    Tier 2 — deep semantic search via FAISS.
    Runs in a background thread because it calls the Gemini embedding API.
    """
    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        results = await asyncio.to_thread(
            rag_service.search_deep, body.query, body.limit
        )
        sys_log.log(
            LogSource.API,
            LogLevel.DEBUG,
            f"search_deep: query='{body.query}' results={len(results)}",
        )
        return SearchResponse(results=[SearchResultItem(**r) for r in results])
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"search_deep failed: {e}")
        return SearchResponse(results=[])


# ==========================================
# Settings Commands
# ==========================================


@commands.command()
async def get_settings(app_handle: AppHandle) -> AppSettings:
    """Return current application settings."""
    import json

    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        rag_service: RAGService = Manager.state(app_handle, RAGService)

        # Read the vault path
        vault_path = str(vault_service.vault_path)

        # Read RAG config from the config dir
        config_dir = rag_service.config_dir
        config_path = config_dir / "rag_config.json"

        # Defaults
        embedding_model = "gemini-embedding-001"
        llm_model = "gemini-2.0-flash"
        google_api_key_raw = ""

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                embedding_model = config_data.get("embedding_model", embedding_model)
                llm_model = config_data.get("llm_model", llm_model)
                google_api_key_raw = config_data.get("google_api_key", "")
            except Exception:
                pass

        # Also check google_api_key.json
        if not google_api_key_raw:
            key_file = config_dir / "google_api_key.json"
            if key_file.exists():
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        key_data = json.load(f)
                    google_api_key_raw = key_data.get("google_api_key", "")
                except Exception:
                    pass

        # Mask the API key
        api_key_set = bool(google_api_key_raw)
        if google_api_key_raw and len(google_api_key_raw) > 4:
            masked_key = "•" * (len(google_api_key_raw) - 4) + google_api_key_raw[-4:]
        elif google_api_key_raw:
            masked_key = "•" * len(google_api_key_raw)
        else:
            masked_key = ""

        # Get auto-save delay from active note default
        auto_save_delay = 2.5

        # Get RAG stats
        rag_status = rag_service.status()

        return AppSettings(
            vault_path=vault_path,
            google_api_key=masked_key,
            google_api_key_set=api_key_set,
            embedding_model=embedding_model,
            llm_model=llm_model,
            auto_save_delay=auto_save_delay,
            rag_enabled=rag_status.get("rag_enabled", False),
            faiss_vectors=rag_status.get("faiss_vectors", 0),
            graph_nodes=rag_status.get("graph_nodes", 0),
            graph_edges=rag_status.get("graph_edges", 0),
        )
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"get_settings failed: {e}")
        raise


@commands.command()
async def save_settings(
    body: SaveSettingsRequest, app_handle: AppHandle
) -> SaveSettingsResponse:
    """Save application settings to config files."""
    import json

    try:
        rag_service: RAGService = Manager.state(app_handle, RAGService)
        config_dir = rag_service.config_dir
        config_path = config_dir / "rag_config.json"
        key_file = config_dir / "google_api_key.json"

        restart_required = False
        changes_made = []

        # Load existing config
        config_data = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                pass

        # Save sushi_settings.json for vault path
        if body.vault_path is not None:
            settings_file = config_dir / "sushi_settings.json"
            settings_data = {}
            if settings_file.exists():
                try:
                    with open(settings_file, "r", encoding="utf-8") as f:
                        settings_data = json.load(f)
                except Exception:
                    pass
            settings_data["vault_path"] = body.vault_path
            
            config_dir.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=2)
                
            restart_required = True
            changes_made.append("vault path")

        # Update embedding model
        if body.embedding_model is not None:
            config_data["embedding_model"] = body.embedding_model
            restart_required = True
            changes_made.append("embedding model")

        # Update LLM model
        if body.llm_model is not None:
            config_data["llm_model"] = body.llm_model
            restart_required = True
            changes_made.append("LLM model")

        # Save rag_config.json
        if changes_made:
            config_dir.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)

        # Handle API key — save to google_api_key.json
        if body.google_api_key is not None:
            # Only save if it's not a masked value (contains • characters)
            if "•" not in body.google_api_key:
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(key_file, "w", encoding="utf-8") as f:
                    json.dump({"google_api_key": body.google_api_key}, f, indent=2)
                restart_required = True
                changes_made.append("API key")

        msg = f"Updated: {', '.join(changes_made)}" if changes_made else "No changes"
        sys_log.log(LogSource.API, LogLevel.INFO, f"save_settings: {msg}")

        return SaveSettingsResponse(
            success=True,
            message=msg + (". Restart required." if restart_required else ""),
            restart_required=restart_required,
        )
    except Exception as e:
        sys_log.log(LogSource.API, LogLevel.ERROR, f"save_settings failed: {e}")
        return SaveSettingsResponse(
            success=False,
            message=str(e),
        restart_required=False,
        )


# ==========================================
# Canvas Commands
# ==========================================


@commands.command()
async def create_canvas_file_cmd(
    body: CreateCanvasFileRequest, app_handle: AppHandle
) -> dict:
    """Create a new canvas file."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        res = vault_service.create_canvas_file(body.title, body.directory)
        return ok(res)
    except Exception as e:
        log.error("create_canvas_failed", error=str(e), title=body.title)
        return err(SAVE_FAILED, str(e))


@commands.command()
async def open_canvas_file_cmd(
    body: OpenCanvasFileRequest, app_handle: AppHandle
) -> dict:
    """Open and load a canvas file, applying migrations."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        data = vault_service.open_canvas_file(body.path)
        return ok({"data": data})
    except FileNotFoundError as e:
        log.error("canvas_not_found", error=str(e), path=body.path)
        return err(CANVAS_NOT_FOUND, str(e))
    except Exception as e:
        log.error("open_canvas_failed", error=str(e), path=body.path)
        return err(LOAD_FAILED, str(e))


@commands.command()
async def save_canvas_file_cmd(
    body: SaveCanvasFileRequest, app_handle: AppHandle
) -> dict:
    """Save an infinite canvas file state."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        vault_service.save_canvas_file(body.file_id, body.path, body.canvas_data)
        return ok({})
    except Exception as e:
        log.error("save_canvas_failed", error=str(e), file_id=body.file_id)
        return err(SAVE_FAILED, str(e))


@commands.command()
async def delete_canvas_file_cmd(
    body: DeleteCanvasFileRequest, app_handle: AppHandle
) -> dict:
    """Delete a canvas file."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        vault_service.delete_canvas_file(body.file_id, body.path)
        return ok({})
    except Exception as e:
        log.error("delete_canvas_failed", error=str(e), file_id=body.file_id)
        return err(SAVE_FAILED, str(e))


@commands.command()
async def rename_canvas_file_cmd(
    body: RenameCanvasFileRequest, app_handle: AppHandle
) -> dict:
    """Rename a canvas or book file on disk and update the database."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        new_path = vault_service.rename_canvas_file(
            body.file_id, body.old_path, body.new_name
        )
        return ok({"new_path": new_path})
    except FileNotFoundError as e:
        log.error("rename_canvas_not_found", error=str(e), file_id=body.file_id)
        return err(CANVAS_NOT_FOUND, str(e))
    except FileExistsError as e:
        log.error("rename_canvas_conflict", error=str(e), file_id=body.file_id)
        return err(SAVE_FAILED, str(e))
    except Exception as e:
        log.error("rename_canvas_failed", error=str(e), file_id=body.file_id)
        return err(SAVE_FAILED, str(e))


@commands.command()
async def get_resource_path_cmd(
    body: GetResourcePathRequest, app_handle: AppHandle
) -> dict:
    """Resolves the absolute OS path for a resource, with lazy integrity checks.

    Routes through ResourceManager.resolve_resource_path() so that missing files
    trigger recovery (canvas) or a regeneration_required signal (thumbnail).
    """
    try:
        from sushi.filesys import get_note_filepath
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        note_path = get_note_filepath(vault_service.db, body.note_id)
        if not note_path:
            return err(NOTE_NOT_FOUND, f"Note {body.note_id} not found")

        result = vault_service.resource_manager.resolve_resource_path(
            filename=body.filename,
            note_dir=note_path.parent,
            block_id=body.block_id,
            block_data=body.block_data,
        )
        return ok(result)
    except Exception as e:
        log.error("get_resource_path_failed", error=str(e), note_id=body.note_id)
        return err(NOTE_NOT_FOUND, str(e))


@commands.command()
async def save_canvas_block_cmd(
    body: SaveCanvasBlockRequest, app_handle: AppHandle
) -> dict:
    """Save an embedded canvas block's data and thumbnail inside a note's resources dir."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        thumb_filename = vault_service.save_canvas_block(
            body.note_id,
            body.block_id,
            body.canvas_ref,
            body.canvas_data,
            body.thumbnail_data_url,
        )
        return ok({"thumbnail_ref": thumb_filename})
    except FileNotFoundError as e:
        log.error("canvas_block_save_note_not_found", error=str(e), note_id=body.note_id)
        return err(NOTE_NOT_FOUND, str(e))
    except Exception as e:
        log.error("canvas_block_save_failed", error=str(e), note_id=body.note_id)
        return err(SAVE_FAILED, str(e))


@commands.command()
async def load_canvas_block_cmd(
    body: LoadCanvasBlockRequest, app_handle: AppHandle
) -> dict:
    """Load an embedded canvas block's stored data from a note's resources dir."""
    try:
        vault_service: VaultService = Manager.state(app_handle, VaultService)
        data = vault_service.load_canvas_block(body.note_id, body.canvas_ref)
        return ok({"data": data})
    except FileNotFoundError as e:
        log.error("canvas_block_load_note_not_found", error=str(e), note_id=body.note_id)
        return err(NOTE_NOT_FOUND, str(e))
    except Exception as e:
        log.error("canvas_block_load_failed", error=str(e), note_id=body.note_id)
        return err(LOAD_FAILED, str(e))
