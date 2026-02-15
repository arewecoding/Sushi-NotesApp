/**
 * Notes Store - State management for notes
 * 
 * Uses Svelte writable stores with async actions for backend communication.
 */

import { writable, derived, get } from 'svelte/store';
import type { NoteListItem, NoteContent, NoteBlock } from '../../client/_apiTypes';
import { getSidebar, openNote, createNote, updateNoteContent, createNoteInDir, deleteNoteById, duplicateNote } from '../../client/apiClient';
import { addToast } from './toastStore';
import { refreshTree } from './fileTreeStore';
import { listen } from '@tauri-apps/api/event';

// Store for list of notes (sidebar)
export const notesList = writable<NoteListItem[]>([]);

// Store for currently active note
export const activeNoteId = writable<string | null>(null);

// Store for the content of the currently open note
export const activeNoteContent = writable<NoteContent | null>(null);

// Version counter - increments on external updates to force UI refresh
export const noteContentVersion = writable(0);

// Loading states
export const isLoadingNotes = writable(false);
export const isLoadingNote = writable(false);
export const isSavingNote = writable(false);


// Debounce timer for auto-save
let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;
const SAVE_DEBOUNCE_MS = 1500; // 1.5 seconds

// Derived store for the currently selected note's metadata
export const activeNoteMetadata = derived(
    [notesList, activeNoteId],
    ([$notesList, $activeNoteId]) => {
        if (!$activeNoteId) return null;
        return $notesList.find(n => n.noteId === $activeNoteId) ?? null;
    }
);

/**
 * Fetch all notes from the backend and update the store.
 */
export async function fetchNotes(): Promise<void> {
    isLoadingNotes.set(true);
    try {
        const notes = await getSidebar();
        notesList.set(notes);
    } catch (error) {
        console.error('Failed to fetch notes:', error);
        addToast('error', 'Failed to load notes');
    } finally {
        isLoadingNotes.set(false);
    }
}

/**
 * Open a note and load its content.
 */
export async function loadNote(noteId: string): Promise<void> {
    isLoadingNote.set(true);
    activeNoteId.set(noteId);

    try {
        const content = await openNote(noteId);
        if (content) {
            activeNoteContent.set(content);
        } else {
            addToast('error', 'Note not found');
            activeNoteContent.set(null);
        }
    } catch (error) {
        console.error('Failed to load note:', error);
        addToast('error', 'Failed to open note');
        activeNoteContent.set(null);
    } finally {
        isLoadingNote.set(false);
    }
}

/**
 * Save the current note content to the backend (debounced).
 * Call this whenever the user edits the title or blocks.
 */
export function saveNoteContentDebounced(title: string, blocks: NoteBlock[]): void {
    const noteId = get(activeNoteId);
    if (!noteId) return;

    // Update the local store immediately for responsive UI
    activeNoteContent.update(content => {
        if (content) {
            return { ...content, title, blocks };
        }
        return content;
    });

    // Clear existing timer and set new one
    if (saveDebounceTimer) {
        clearTimeout(saveDebounceTimer);
    }

    isSavingNote.set(true);

    saveDebounceTimer = setTimeout(async () => {
        try {
            const result = await updateNoteContent(noteId, title, blocks);
            if (result.success) {
                console.log('Note saved successfully');
            } else {
                console.error('Failed to save note:', result.message);
                addToast('error', 'Failed to save note');
            }
        } catch (error) {
            console.error('Failed to save note:', error);
            addToast('error', 'Failed to save note');
        } finally {
            isSavingNote.set(false);
        }
    }, SAVE_DEBOUNCE_MS);
}

/**
 * Create a new note and add it to the list.
 */
export async function addNewNote(title: string = 'Untitled Note'): Promise<string | null> {
    try {
        const newNote = await createNote(title);
        if (newNote) {
            // Add to the notes list
            notesList.update(notes => [...notes, newNote]);
            refreshTree();
            addToast('success', `Created "${newNote.noteTitle}"`);
            return newNote.noteId;
        } else {
            addToast('error', 'Failed to create note');
            return null;
        }
    } catch (error) {
        console.error('Failed to create note:', error);
        addToast('error', 'Failed to create note');
        return null;
    }
}

/**
 * Create a new note and immediately open it.
 * If dirPath is provided, creates the note in that directory.
 */
export async function createAndOpenNote(title: string = 'Untitled Note', dirPath?: string | null): Promise<void> {
    let noteId: string | null = null;
    if (dirPath) {
        try {
            const newNote = await createNoteInDir(title, dirPath);
            if (newNote) {
                notesList.update(notes => [...notes, newNote]);
                refreshTree();
                addToast('success', `Created "${newNote.noteTitle}"`);
                noteId = newNote.noteId;
            }
        } catch (error) {
            console.error('Failed to create note in dir:', error);
            addToast('error', 'Failed to create note');
        }
    } else {
        noteId = await addNewNote(title);
    }
    if (noteId) {
        await loadNote(noteId);
    }
}

/**
 * Delete a note by ID. Clears active note if it's the one being deleted.
 */
export async function deleteNoteAction(noteId: string): Promise<boolean> {
    try {
        const result = await deleteNoteById(noteId);
        if (result.success) {
            // Clear active note if it was the deleted one
            const currentId = get(activeNoteId);
            if (currentId === noteId) {
                activeNoteId.set(null);
                activeNoteContent.set(null);
            }
            // Remove from sidebar list
            notesList.update(notes => notes.filter(n => n.noteId !== noteId));
            refreshTree();
            addToast('success', 'Note deleted');
            return true;
        } else {
            addToast('error', result.message || 'Failed to delete note');
            return false;
        }
    } catch (error) {
        console.error('Failed to delete note:', error);
        addToast('error', 'Failed to delete note');
        return false;
    }
}

/**
 * Duplicate a note. Creates 'Copy of ...' beside the original.
 */
export async function duplicateNoteAction(noteId: string): Promise<string | null> {
    try {
        const copy = await duplicateNote(noteId);
        if (copy) {
            notesList.update(notes => [...notes, copy]);
            refreshTree();
            addToast('success', `Created "${copy.noteTitle}"`);
            return copy.noteId;
        } else {
            addToast('error', 'Failed to duplicate note');
            return null;
        }
    } catch (error) {
        console.error('Failed to duplicate note:', error);
        addToast('error', 'Failed to duplicate note');
        return null;
    }
}

/**
 * Setup event listeners for note-related backend events.
 * Should be called once during app initialization.
 */
export function setupNoteEventListeners(): () => void {
    // Listen for external note changes (e.g., file edited in Notepad)
    const unlisten = listen<{ noteId: string }>("note-content-changed", async (event) => {
        const changedNoteId = event.payload.noteId;
        const currentNoteId = get(activeNoteId);

        console.log("Note content changed externally:", changedNoteId);

        // If the changed note is currently active, reload it
        if (changedNoteId && changedNoteId === currentNoteId) {
            console.log("Reloading active note due to external change");
            // Reload the note content from backend
            try {
                const content = await openNote(changedNoteId);
                if (content) {
                    activeNoteContent.set(content);
                    // Increment version to force UI refresh even if block IDs unchanged
                    noteContentVersion.update(v => v + 1);
                    addToast('info', 'Note updated from external changes');
                }
            } catch (error) {
                console.error('Failed to reload note after external change:', error);
            }
        }
    });

    // Listen for external note deletion — close the editor if active note was deleted
    const unlistenDeleted = listen<{ noteId: string }>("note-deleted", (event) => {
        const deletedNoteId = event.payload.noteId;
        const currentNoteId = get(activeNoteId);

        console.log("Note deleted externally:", deletedNoteId);

        if (deletedNoteId && deletedNoteId === currentNoteId) {
            activeNoteId.set(null);
            activeNoteContent.set(null);
            addToast('warning', 'The open note was deleted');
        }
    });

    // Return cleanup function
    return () => {
        unlisten.then((fn) => fn());
        unlistenDeleted.then((fn) => fn());
    };
}

