/**
 * blockFactory.ts
 * ===============
 * Factory functions for creating NoteBlock objects in the frontend editor.
 * Generates short block IDs and provides default data structures per block type.
 */

import type { NoteBlock } from "$lib/client/_apiTypes";

/**
 * Generate a short 16-character block ID from a UUID.
 * Strips hyphens and truncates for compactness.
 */
export function generateBlockId(): string {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
}

/**
 * Create a new NoteBlock with sensible defaults for the given type.
 * Supports: text, todo, code, latex.
 */
export function createBlock(type: string): NoteBlock {
    return {
        blockId: generateBlockId(),
        type,
        data:
            type === "code"
                ? { code: "" }
                : type === "todo"
                    ? { content: "", checked: false }
                    : type === "latex"
                        ? { content: "" }
                        : { content: "" },
        version: "1",
        tags: [],
        backlinks: [],
    };
}
