/**
 * View Store — Discriminated union routing for the main content area.
 *
 * Tracks what the user is currently looking at: a note, a canvas,
 * a notebook, or nothing. The sidebar and other navigation sources
 * call openFile() / openNote() to update this state.
 */

import { writable, get } from "svelte/store";
import { loadNote, activeNoteId, activeNoteContent } from "./notesStore";

// ── View type ───────────────────────────────────────────────────────
export type MainAreaView =
    | { type: "note"; noteId: string }
    | { type: "canvas"; canvasId: string; filePath: string }
    | { type: "book"; bookId: string; filePath: string }
    | { type: "empty" };

export const currentView = writable<MainAreaView>({ type: "empty" });

// ── Navigation helpers ──────────────────────────────────────────────

/**
 * Open any vault file based on its type. Called from the sidebar.
 * Maps file_type → MainAreaView discriminant and triggers the
 * appropriate backend load for notes.
 */
export async function openFile(file: {
    id: string;
    fileType: string;
    filePath?: string;
}): Promise<void> {
    switch (file.fileType) {
        case "jnote":
            // Delegate to the existing note loading pipeline
            currentView.set({ type: "note", noteId: file.id });
            await loadNote(file.id);
            break;
        case "jcanvas":
            // Clear note state so MainArea doesn't show stale note
            activeNoteId.set(null);
            activeNoteContent.set(null);
            currentView.set({
                type: "canvas",
                canvasId: file.id,
                filePath: file.filePath ?? "",
            });
            break;
        case "jbook":
            activeNoteId.set(null);
            activeNoteContent.set(null);
            currentView.set({
                type: "book",
                bookId: file.id,
                filePath: file.filePath ?? "",
            });
            break;
        default:
            console.warn(`Unknown file type: ${file.fileType}`);
    }
}

/**
 * Open a note by ID. Convenience wrapper that keeps backward compat
 * with call sites that only know the noteId (e.g. linked-note navigation).
 */
export async function openNoteView(noteId: string): Promise<void> {
    currentView.set({ type: "note", noteId });
    await loadNote(noteId);
}
