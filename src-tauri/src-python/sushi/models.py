"""
Sushi IPC Models
=================
All Pydantic models for PyTauri IPC communication.
Includes request/response DTOs and event payloads.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Dict, Any, Optional, List


# ==========================================
# Base Configuration
# ==========================================


class PyTauriModel(BaseModel):
    """Base model with automatic snake_case ↔ camelCase conversion."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        serialize_by_alias=True,
    )


# ==========================================
# Request Models (Frontend → Backend)
# ==========================================


class OpenNoteRequest(PyTauriModel):
    note_id: str


class CreateNoteRequest(PyTauriModel):
    title: str = "Untitled Note"


class UpdateNoteContentRequest(PyTauriModel):
    """Full note content update (title + blocks)."""

    note_id: str
    title: str
    blocks: List[Dict[str, Any]]


class GetDirectoryRequest(PyTauriModel):
    """Request directory contents. None/empty = vault root."""

    dir_path: Optional[str] = None


class CreateBlockRequest(PyTauriModel):
    note_id: str
    block_type: str
    content_data: Dict[str, Any]


class UpdateBlockRequest(PyTauriModel):
    note_id: str
    block_id: str
    new_data: Dict[str, Any]


class DeleteBlockRequest(PyTauriModel):
    note_id: str
    block_id: str


class VaultConfig(PyTauriModel):
    path: str


class CreateNoteInDirRequest(PyTauriModel):
    """Create a note in a specific directory."""

    title: str = "Untitled Note"
    dir_path: str


class DeleteNoteRequest(PyTauriModel):
    note_id: str


class DeleteDirectoryRequest(PyTauriModel):
    dir_path: str


class MoveItemRequest(PyTauriModel):
    """Move a file or directory to a destination directory."""

    source_path: str
    dest_dir: str


class DuplicateNoteRequest(PyTauriModel):
    note_id: str


class MoveNoteRequest(PyTauriModel):
    """Move a note (by ID) to a destination directory."""

    note_id: str
    dest_dir: str


class CreateDirectoryRequest(PyTauriModel):
    parent_path: str
    dir_name: str


class RenameNoteRequest(PyTauriModel):
    """Rename a note by ID."""

    note_id: str
    new_title: str


class RenameDirectoryRequest(PyTauriModel):
    """Rename a directory."""

    dir_path: str
    new_name: str


# ==========================================
# Response Models (Backend → Frontend)
# ==========================================


class OperationResponse(PyTauriModel):
    success: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None


class NoteListItem(PyTauriModel):
    """Simplified note metadata for sidebar display."""

    note_id: str
    note_title: str


class NoteContent(PyTauriModel):
    """Full note content returned to frontend."""

    note_id: str
    title: str
    blocks: List[Dict[str, Any]]


class DirectoryItem(PyTauriModel):
    """A directory in the file tree."""

    dir_path: str
    dir_name: str


class DirectoryContents(PyTauriModel):
    """Contents of a directory — subdirs and notes."""

    subdirs: List[DirectoryItem]
    notes: List[NoteListItem]


# ==========================================
# Event Payloads (Backend → Frontend via Emitter)
# ==========================================


class TreeChangedPayload(PyTauriModel):
    """Payload for tree-changed event."""

    changed_path: str
    event_type: str  # 'created', 'deleted', 'moved'


class NoteContentChangedPayload(PyTauriModel):
    """Payload for note-content-changed event (external edits)."""

    note_id: str


class NoteDeletedPayload(PyTauriModel):
    """Payload for note-deleted event (external file deletion)."""

    note_id: str


class VaultReadyPayload(PyTauriModel):
    """Payload for vault-ready event (backend initialization complete)."""

    pass


# ==========================================
# RAG Request / Response Models
# ==========================================


class RagQueryRequest(PyTauriModel):
    """Ask the RAG pipeline a natural-language question over the notes vault."""

    query: str


class RagQueryResponse(PyTauriModel):
    """Full result from a RAG pipeline run."""

    answer: str
    strategy: str  # 'direct_recall' | 'contextual_traversal' | 'disabled' | 'error'
    query_original: str
    query_optimized: str
    blocks_retrieved: int
    blocks_reranked: int
    blocks_in_context: int
    context_truncated: bool
    latency: Dict[str, float]
    rag_enabled: bool


class RagBuildIndexRequest(PyTauriModel):
    """Trigger a full rebuild of the RAG index over the entire vault.

    No parameters — always rebuilds from the vault root configured at startup.
    """

    pass


class RagBuildIndexResponse(PyTauriModel):
    """Statistics returned after a full index rebuild."""

    status: str  # 'ok' | 'error' | 'disabled'
    notes_indexed: int
    blocks_indexed: int
    graph_nodes: int
    graph_edges: int
    rag_enabled: bool
    message: str = ""


class RagStatusResponse(PyTauriModel):
    """Health snapshot of the RAG index."""

    rag_enabled: bool
    faiss_vectors: int
    tombstone_ratio: float
    graph_nodes: int
    graph_edges: int
    message: str


# ==========================================
# Search Request / Response Models
# ==========================================


class SearchRequest(PyTauriModel):
    """Search query for Tier 1 (fast) or Tier 2 (deep)."""

    query: str
    limit: int = 10


class SearchResultItem(PyTauriModel):
    """A single search result — either a note or a block."""

    result_type: str  # "note" | "block"
    note_id: str
    note_title: str
    block_id: Optional[str] = None
    block_snippet: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(PyTauriModel):
    """Search results returned to the frontend."""

    results: List[SearchResultItem]
