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
