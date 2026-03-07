/**
 * linkParser.ts
 * =============
 * Parses inline link tokens from block text.
 *
 * PRIMARY SYNTAX (new):
 *   [[Display Text||note||<note_uuid>]]
 *   [[Display Text||block||<note_uuid>/<block_uuid>]]
 *   [[Display Text||web||https://example.com]]
 *
 * LEGACY SYNTAX (backward-compat, treated as note/block link):
 *   [[Display Text|<note_uuid>]]
 *   [[Display Text|<note_uuid>/<block_uuid>]]
 *
 * Rendering behaviour:
 *   - "note"  → orange span, click navigates to note
 *   - "block" → amber span, click navigates to note and scrolls block into view
 *   - "web"   → sky-blue span with ↗ icon, click opens URL in default browser
 */

export type TextToken = {
    type: "text";
    raw: string;
};

export type LinkToken = {
    type: "link";
    raw: string;          // full [[...]] string — stored verbatim in note content
    display: string;      // human-readable label
    linkType: "note" | "block" | "web";
    noteId: string | null;   // for note + block links
    blockId: string | null;  // for block links only
    url: string | null;      // for web links only
};

export type Token = TextToken | LinkToken;

// ── Patterns ─────────────────────────────────────────────────────────────────

/** New primary format: [[display||type||target]] */
const NEW_PATTERN =
    /\[\[([^\]|]+)\|\|(note|block|web)\|\|([^\]]+)\]\]/g;

/** Legacy format: [[display|uuid]] or [[display|uuid/uuid]] */
const LEGACY_PATTERN =
    /\[\[([^\]|]+)\|([0-9a-f-]{32,36})(?:\/([0-9a-f-]{32,36}))?\]\]/g;

// ── Token building ────────────────────────────────────────────────────────────

function newMatch(raw: string, display: string, linkType: string, target: string): LinkToken {
    if (linkType === "web") {
        return { type: "link", raw, display, linkType: "web", noteId: null, blockId: null, url: target.trim() };
    }
    if (linkType === "block") {
        const [noteId, blockId] = target.trim().split("/");
        return { type: "link", raw, display, linkType: "block", noteId: noteId ?? null, blockId: blockId ?? null, url: null };
    }
    // "note"
    return { type: "link", raw, display, linkType: "note", noteId: target.trim(), blockId: null, url: null };
}

function legacyMatch(raw: string, display: string, noteId: string, blockId?: string): LinkToken {
    if (blockId) {
        return { type: "link", raw, display, linkType: "block", noteId, blockId, url: null };
    }
    return { type: "link", raw, display, linkType: "note", noteId, blockId: null, url: null };
}

// ── Main parse ────────────────────────────────────────────────────────────────

/**
 * Parse a block's text content into an ordered array of text/link tokens.
 * We collect matches from both patterns, sort by position, and emit tokens.
 */
export function parseLinks(text: string): Token[] {
    // Collect all matches with their positions
    type RawMatch = { start: number; end: number; token: LinkToken };
    const matches: RawMatch[] = [];

    for (const m of text.matchAll(NEW_PATTERN)) {
        const start = m.index!;
        matches.push({
            start,
            end: start + m[0].length,
            token: newMatch(m[0], m[1].trim(), m[2], m[3]),
        });
    }
    for (const m of text.matchAll(LEGACY_PATTERN)) {
        const start = m.index!;
        // Skip if this range is already covered by a new-format match
        if (matches.some((x) => start >= x.start && start < x.end)) continue;
        matches.push({
            start,
            end: start + m[0].length,
            token: legacyMatch(m[0], m[1].trim(), m[2], m[3]),
        });
    }

    matches.sort((a, b) => a.start - b.start);

    const tokens: Token[] = [];
    let cursor = 0;

    for (const { start, end, token } of matches) {
        if (start > cursor) {
            tokens.push({ type: "text", raw: text.slice(cursor, start) });
        }
        tokens.push(token);
        cursor = end;
    }

    if (cursor < text.length) {
        tokens.push({ type: "text", raw: text.slice(cursor) });
    }

    return tokens;
}

// ── Utilities ─────────────────────────────────────────────────────────────────

/**
 * Serialise a link back to its [[...]] storage format.
 */
export function serializeLink(
    display: string,
    linkType: "note" | "block" | "web",
    target: string          // noteId, noteId/blockId, or URL
): string {
    return `[[${display}||${linkType}||${target}]]`;
}

/**
 * Extract all note IDs referenced in a block's text (for backlink tracking).
 */
export function extractNoteIds(text: string): string[] {
    const ids: string[] = [];
    for (const tok of parseLinks(text)) {
        if (tok.type === "link" && tok.noteId) {
            ids.push(tok.noteId);
        }
    }
    return [...new Set(ids)];
}

/**
 * Check whether a character offset falls within a link token.
 */
export function findLinkAtOffset(
    text: string,
    offset: number
): { token: LinkToken; start: number; end: number } | null {
    const tokens = parseLinks(text);
    let pos = 0;
    for (const tok of tokens) {
        const end = pos + tok.raw.length;
        if (tok.type === "link" && offset >= pos && offset <= end) {
            return { token: tok, start: pos, end };
        }
        pos = end;
    }
    return null;
}
