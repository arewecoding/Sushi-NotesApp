/**
 * PyTauri Notes App - API Client
 * 
 * This module provides type-safe wrappers for calling backend Python commands
 * via the tauri-plugin-pytauri-api's pyInvoke function.
 */

import { pyInvoke } from "tauri-plugin-pytauri-api";
import type { InvokeOptions } from "@tauri-apps/api/core";
import type {
    NoteListItem,
    NoteContent,
    NoteBlock,
    OperationResponse,
    CreateBlockRequest,
    UpdateBlockRequest,
    DeleteBlockRequest,
    DirectoryContents,
} from "./_apiTypes";

/**
 * Fetches the contents of a directory (subdirs and notes).
 * @param dirPath - Path to the directory, or null for vault root
 */
export async function getDirectoryContents(
    dirPath?: string | null,
    options?: InvokeOptions
): Promise<DirectoryContents> {
    return await pyInvoke("get_directory_contents", { dirPath }, options);
}

/**
 * Fetches all notes for the sidebar navigation.
 * @returns List of note metadata (id and title)
 */
export async function getSidebar(
    options?: InvokeOptions
): Promise<NoteListItem[]> {
    return await pyInvoke("get_sidebar", null, options);
}

/**
 * Opens a note and returns its full content.
 * @param noteId - The unique identifier of the note to open
 */
export async function openNote(
    noteId: string,
    options?: InvokeOptions
): Promise<NoteContent | null> {
    return await pyInvoke("open_note", { noteId }, options);
}

/**
 * Updates a note's content (title and all blocks).
 * @param noteId - The note ID
 * @param title - The new title
 * @param blocks - The updated blocks array
 */
export async function updateNoteContent(
    noteId: string,
    title: string,
    blocks: NoteBlock[],
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("update_note_content", { noteId, title, blocks }, options);
}

/**
 * Creates a new note with the given title.
 * @param title - The title for the new note
 */
export async function createNote(
    title: string = "Untitled Note",
    options?: InvokeOptions
): Promise<NoteListItem | null> {
    return await pyInvoke("create_note", { title }, options);
}

/**
 * Adds a new block to an open note.
 */
export async function addBlock(
    request: CreateBlockRequest,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("add_block", request, options);
}

/**
 * Updates an existing block in an open note.
 */
export async function updateBlock(
    request: UpdateBlockRequest,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("update_block", request, options);
}

/**
 * Deletes a block from an open note.
 */
export async function deleteBlock(
    request: DeleteBlockRequest,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("delete_block", request, options);
}
