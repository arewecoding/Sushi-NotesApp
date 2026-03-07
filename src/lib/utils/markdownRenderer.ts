/**
 * markdownRenderer.ts
 * ===================
 * Rendering pipeline: markdown (marked) + LaTeX (KaTeX) + [[links]].
 * View mode:  renderViewHtml() — full block render
 * Edit mode:  renderLineHtml() — per-line render for Obsidian-style editing
 */
import { marked } from "marked";
import katex from "katex";
import { parseLinks } from "./linkParser";

// ── Utilities ───────────────────────────────────────────────────────────────

export function escapeHtml(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderKatex(math: string, display: boolean): string {
    try {
        return katex.renderToString(math, {
            displayMode: display,
            throwOnError: false,
            output: "html",
        });
    } catch {
        return `<span class="katex-error">${display ? "$$" : "$"}${escapeHtml(math)}${display ? "$$" : "$"}</span>`;
    }
}

// Configure marked once
marked.use({ breaks: true, gfm: true });

// ── View-mode rendering ─────────────────────────────────────────────────────

/** Build a link HTML span from a raw [[...]] token. */
function linkToHtml(
    raw: string,
    notesList: Array<{ noteId: string; noteTitle: string }>
): string {
    for (const tok of parseLinks(raw)) {
        if (tok.type !== "link") continue;
        const title =
            tok.noteId
                ? (notesList.find((n) => n.noteId === tok.noteId)?.noteTitle ??
                    tok.display)
                : tok.display;
        const d = encodeURIComponent(raw);
        if (tok.linkType === "note")
            return `<span class="note-link note-link--note" data-link-type="note" data-note-id="${tok.noteId ?? ""}" data-raw="${d}" title="→ ${title}" contenteditable="false">${tok.display}</span>`;
        if (tok.linkType === "block")
            return `<span class="note-link note-link--block" data-link-type="block" data-note-id="${tok.noteId ?? ""}" data-block-id="${tok.blockId ?? ""}" data-raw="${d}" title="⚓ ${title} › block" contenteditable="false">${tok.display}</span>`;
        return `<span class="note-link note-link--web" data-link-type="web" data-url="${encodeURIComponent(tok.url ?? "")}" data-raw="${d}" title="↗ ${tok.url}" contenteditable="false">${tok.display} ↗</span>`;
    }
    return escapeHtml(raw);
}

/**
 * Full render for view mode: markdown → KaTeX → links.
 */
export function renderViewHtml(
    rawText: string,
    notesList: Array<{ noteId: string; noteTitle: string }>
): string {
    if (!rawText.trim()) return "";

    // 1. Extract [[links]] → placeholders so marked doesn't mangle them
    const linkRaws: string[] = [];
    let text = rawText.replace(/\[\[[^\]]+\]\]/g, (m) => {
        const i = linkRaws.push(m) - 1;
        return `LNKPH${i}END`;
    });

    // 2. Markdown → HTML
    let html = marked.parse(text) as string;

    // 3. KaTeX — display ($$) before inline ($)
    html = html.replace(/\$\$([^$]+?)\$\$/gs, (_, m) => renderKatex(m, true));
    html = html.replace(/\$([^$\n]+?)\$/g, (_, m) => renderKatex(m, false));

    // 4. Restore links
    html = html.replace(/LNKPH(\d+)END/g, (_, i) =>
        linkToHtml(linkRaws[Number(i)], notesList)
    );

    return html;
}

// ── Edit-mode: per-line renderer (Obsidian approach) ────────────────────────

/**
 * Render a single raw markdown line to HTML — no <p> wrapper.
 * Used in Obsidian-style edit mode where each line can be independently
 * rendered or shown as raw syntax when the cursor is on it.
 */
export function renderLineHtml(
    line: string,
    notesList: Array<{ noteId: string; noteTitle: string }>
): string {
    // Blank line — keep height with a non-breaking space
    if (!line.trim()) return "\u00A0";

    // Extract [[links]] → placeholders before marked touches them
    const linkRaws: string[] = [];
    const withPH = line.replace(/\[\[[^\]]+\]\]/g, (m) => {
        const i = linkRaws.push(m) - 1;
        return `LNKPH${i}END`;
    });

    // Helper: restore links + apply KaTeX to an inline HTML string
    function finalize(html: string): string {
        html = html.replace(/\$([^$\n]+?)\$/g, (_, m) => renderKatex(m, false));
        html = html.replace(/LNKPH(\d+)END/g, (_, i) =>
            linkToHtml(linkRaws[Number(i)], notesList)
        );
        return html;
    }

    // ── Block-level detections ─────────────────────────────────────────────

    // Heading: # … ###### …
    const hMatch = withPH.match(/^(#{1,6}) (.*)/);
    if (hMatch) {
        const lvl = hMatch[1].length;
        const inner = finalize(marked.parseInline(hMatch[2]) as string);
        return `<h${lvl} class="md-h${lvl}">${inner}</h${lvl}>`;
    }

    // Horizontal rule
    if (/^(---+|\*\*\*+|___+)$/.test(withPH.trim())) {
        return `<hr class="md-hr">`;
    }

    // Blockquote: > …
    const bqMatch = withPH.match(/^> (.*)/);
    if (bqMatch) {
        const inner = finalize(marked.parseInline(bqMatch[1]) as string);
        return `<span class="md-bq">${inner}</span>`;
    }

    // Unordered list item: - / * / +
    const ulMatch = withPH.match(/^([*\-+]) (.*)/);
    if (ulMatch) {
        const inner = finalize(marked.parseInline(ulMatch[2]) as string);
        return `<span class="md-li"><span class="md-li-dot">•</span><span class="md-li-text">${inner}</span></span>`;
    }

    // Ordered list item: 1. / 2. …
    const olMatch = withPH.match(/^(\d+)\. (.*)/);
    if (olMatch) {
        const inner = finalize(marked.parseInline(olMatch[2]) as string);
        return `<span class="md-li"><span class="md-li-dot">${olMatch[1]}.</span><span class="md-li-text">${inner}</span></span>`;
    }

    // Code fence start/end  (show raw — fences are handled by full-block render)
    if (/^```/.test(withPH)) return escapeHtml(line);

    // ── Plain inline text ──────────────────────────────────────────────────
    const html = finalize(marked.parseInline(withPH) as string);
    return html;
}
