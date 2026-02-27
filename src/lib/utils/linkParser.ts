/**
 * linkParser.ts
 * =============
 * Pure utility for parsing [[display text|target_id]] link tokens from block text.
 *
 * Link syntax:  [[Display Text|note_id]]
 *               [[Display Text|note_id/block_id]]
 *
 * When rendered the full [[...]] is hidden and only "Display Text" is shown
 * as a styled link. When the text cursor enters the token, the raw syntax
 * is revealed for editing.
 */

export type TextToken = {
    type: "text";
    raw: string;
};

export type LinkToken = {
    type: "link";
    raw: string;         // full [[...]] including brackets — stored in content
    display: string;     // text before the |
    noteId: string;      // note_id (everything after | before optional /)
    blockId: string | null; // optional block_id after /
};

export type Token = TextToken | LinkToken;

// Matches [[display text|note_id]] or [[display text|note_id/block_id]]
// note_id and block_id are hex strings (16 chars)
const LINK_PATTERN = /\[\[([^\]|]+)\|([0-9a-f]{16})(?:\/([0-9a-f]{16}))?\]\]/g;

/**
 * Parse a block's text content into an array of text/link tokens.
 */
export function parseLinks(text: string): Token[] {
    const tokens: Token[] = [];
    let lastIndex = 0;

    for (const match of text.matchAll(LINK_PATTERN)) {
        const matchStart = match.index!;
        const matchEnd = matchStart + match[0].length;

        // Text before this match
        if (matchStart > lastIndex) {
            tokens.push({ type: "text", raw: text.slice(lastIndex, matchStart) });
        }

        tokens.push({
            type: "link",
            raw: match[0],
            display: match[1].trim(),
            noteId: match[2],
            blockId: match[3] ?? null,
        });

        lastIndex = matchEnd;
    }

    // Remaining text
    if (lastIndex < text.length) {
        tokens.push({ type: "text", raw: text.slice(lastIndex) });
    }

    return tokens;
}

/**
 * Check whether a given character offset inside `text` falls within a link token.
 * Returns the token and its start/end range if so, or null.
 */
export function findLinkAtOffset(
    text: string,
    offset: number
): { token: LinkToken; start: number; end: number } | null {
    for (const match of text.matchAll(LINK_PATTERN)) {
        const start = match.index!;
        const end = start + match[0].length;
        if (offset >= start && offset <= end) {
            return {
                token: {
                    type: "link",
                    raw: match[0],
                    display: match[1].trim(),
                    noteId: match[2],
                    blockId: match[3] ?? null,
                },
                start,
                end,
            };
        }
    }
    return null;
}

/**
 * Serialise a link back to its [[...]] storage format.
 */
export function serializeLink(display: string, noteId: string, blockId?: string | null): string {
    if (blockId) return `[[${display}|${noteId}/${blockId}]]`;
    return `[[${display}|${noteId}]]`;
}

/**
 * Extract all note IDs referenced in a block's text (for backlink tracking).
 */
export function extractNoteIds(text: string): string[] {
    const ids: string[] = [];
    for (const match of text.matchAll(LINK_PATTERN)) {
        ids.push(match[2]);
    }
    return [...new Set(ids)];
}
