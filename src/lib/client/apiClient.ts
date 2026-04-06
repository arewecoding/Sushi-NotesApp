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
    DirectoryContents,
    SearchResponse,
    AppSettings,
    SaveSettingsResponse,
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


// ==========================================
// File Tree CRUD Operations
// ==========================================

/**
 * Creates a new note in a specific directory.
 */
export async function createNoteInDir(
    title: string,
    dirPath: string,
    options?: InvokeOptions
): Promise<NoteListItem | null> {
    return await pyInvoke("create_note_in_dir", { title, dirPath }, options);
}

/**
 * Deletes a note by ID (closes if active, removes file).
 */
export async function deleteNoteById(
    noteId: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("delete_note_cmd", { noteId }, options);
}

/**
 * Deletes a directory and all its contents.
 */
export async function deleteDirectoryByPath(
    dirPath: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("delete_directory_cmd", { dirPath }, options);
}

/**
 * Moves a note or directory to another directory.
 */
export async function moveItem(
    sourcePath: string,
    destDir: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("move_item_cmd", { sourcePath, destDir }, options);
}

/**
 * Creates an exact copy of a note with 'Copy of' prefix.
 */
export async function duplicateNote(
    noteId: string,
    options?: InvokeOptions
): Promise<NoteListItem | null> {
    return await pyInvoke("duplicate_note_cmd", { noteId }, options);
}

/**
 * Creates a new subdirectory.
 */
export async function createDirectoryIn(
    parentPath: string,
    dirName: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("create_directory_cmd", { parentPath, dirName }, options);
}

/**
 * Moves a note by ID to a destination directory.
 */
export async function moveNoteById(
    noteId: string,
    destDir: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("move_note_cmd", { noteId, destDir }, options);
}

/**
 * Renames a note by ID.
 */
export async function renameNoteById(
    noteId: string,
    newTitle: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("rename_note_cmd", { noteId, newTitle }, options);
}

/**
 * Renames a directory.
 */
export async function renameDirectoryByPath(
    dirPath: string,
    newName: string,
    options?: InvokeOptions
): Promise<OperationResponse> {
    return await pyInvoke("rename_directory_cmd", { dirPath, newName }, options);
}

// ==========================================
// Search Operations
// ==========================================



/**
 * Tier 1 — fast keyword search (titles + FTS5 block content).
 * No embedding API calls, sub-10ms.
 */
export async function searchFast(
    query: string,
    limit: number = 10,
    options?: InvokeOptions
): Promise<SearchResponse> {
    return await pyInvoke("search_fast", { query, limit }, options);
}

/**
 * Tier 2 — deep semantic search via FAISS.
 * Calls the Gemini embedding API (~200-600ms latency).
 */
export async function searchDeep(
    query: string,
    limit: number = 10,
    options?: InvokeOptions
): Promise<SearchResponse> {
    return await pyInvoke("search_deep", { query, limit }, options);
}

// ── Settings ────────────────────────────────────────────────────────────

/**
 * Fetch current application settings.
 */
export async function getSettings(
    options?: InvokeOptions
): Promise<AppSettings> {
    return await pyInvoke("get_settings", null, options);
}

/**
 * Save application settings.
 */
export async function saveSettings(
    settings: {
        vaultPath?: string | null;
        googleApiKey?: string | null;
        embeddingModel?: string | null;
        llmModel?: string | null;
        autoSaveDelay?: number | null;
    },
    options?: InvokeOptions
): Promise<SaveSettingsResponse> {
    return await pyInvoke("save_settings", settings, options);
}

/**
 * Fetches the absolute path of a `.sushi-resources` file and returns it as a Tauri asset:// URL.
 * Enables local files to load in `<img>` tags on the frontend.
 */
export async function getResourcePath(
    noteId: string, 
    filename: string,
    blockId?: string,
    blockData?: object,
    options?: InvokeOptions
): Promise<string | { status: 'regeneration_required', canvasData: any, lastViewport: any } | null> {
    const res = await pyInvoke("get_resource_path_cmd", { noteId, filename, blockId, blockData }, options);
    // Backend returns ok(result) → {status: "ok", data: {status: "ok", path: "..."}}
    // OR {status: "ok", data: {status: "regeneration_required", canvas_data: ..., last_viewport: ...}}
    const data = (res as any)?.data;
    
    if (data?.status === 'regeneration_required') {
        return {
            status: 'regeneration_required',
            canvasData: data.canvas_data,
            lastViewport: data.last_viewport
        };
    }
    
    return data?.path || null;
}

/**
 * Creates a structural block on the backend, saves it into the active note,
 * and returns the populated schema back to the frontend.
 */
export async function createBlockCmd(
    noteId: string,
    blockType: string,
    contentData: object = {},
    options?: InvokeOptions
): Promise<any | null> {
    return await pyInvoke("create_block_cmd", { noteId, blockType, contentData }, options);
}
