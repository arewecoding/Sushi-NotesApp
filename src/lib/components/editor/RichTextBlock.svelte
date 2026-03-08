<script lang="ts">
    /**
     * RichTextBlock.svelte — Simple text block editor
     * ================================================
     * VIEW (not focused): rendered HTML via renderViewHtml()
     * EDIT (focused):     plain text in <div> per line, no rendering
     *
     * Arrow keys, Enter, Backspace — all handled by the browser natively.
     * No line activation, no selection tracking, no beforeinput interception.
     */

    import { renderViewHtml, escapeHtml } from "$lib/utils/markdownRenderer";
    import { openUrl } from "@tauri-apps/plugin-opener";

    interface Props {
        blockId: string;
        initialContent: string;
        notesList: Array<{ noteId: string; noteTitle: string }>;
        onchange: (blockId: string, text: string) => void;
        onnavigate: (noteId: string, blockId: string | null) => void;
        className?: string;
    }

    let {
        blockId,
        initialContent,
        notesList,
        onchange,
        onnavigate,
        className = "",
    }: Props = $props();

    let editorEl = $state<HTMLElement | null>(null);
    let plainText = $state(initialContent);
    let isFocused = $state(false);

    // ── Lifecycle ──────────────────────────────────────────────────────────

    $effect(() => {
        const el = editorEl;
        if (el && !isFocused) {
            el.innerHTML = renderViewHtml(plainText, notesList);
        }
    });

    $effect(() => {
        const _list = notesList;
        const el = editorEl;
        if (el && !isFocused) {
            el.innerHTML = renderViewHtml(plainText, notesList);
        }
    });

    // ── Event handlers ─────────────────────────────────────────────────────

    function handleFocus() {
        isFocused = true;
        if (!editorEl) return;

        // Build one <div> per line with raw text — browser handles all editing
        const rawLines = plainText.split("\n");
        editorEl.innerHTML = rawLines
            .map((line) => `<div>${escapeHtml(line) || "<br>"}</div>`)
            .join("");

        // Place cursor at end
        const sel = window.getSelection();
        if (sel) {
            const range = document.createRange();
            range.selectNodeContents(editorEl);
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
        }
    }

    function handleBlur() {
        isFocused = false;
        if (!editorEl) return;
        const raw = editorEl.innerText ?? "";
        plainText = raw;
        onchange(blockId, raw);
        editorEl.innerHTML = renderViewHtml(raw, notesList);
    }

    function handleInput() {
        if (!editorEl) return;
        plainText = editorEl.innerText ?? "";
        onchange(blockId, plainText);
    }

    function handleMouseDown(e: MouseEvent) {
        const target = e.target as HTMLElement;
        const linkEl = target.closest(".note-link") as HTMLElement | null;
        if (!linkEl) return;
        if (isFocused) return;

        e.preventDefault();
        const linkType = linkEl.dataset.linkType;
        if (linkType === "web") {
            const url = decodeURIComponent(linkEl.dataset.url ?? "");
            if (url) openUrl(url).catch(console.error);
        } else if (linkType === "block") {
            const noteId = linkEl.dataset.noteId;
            const blkId = linkEl.dataset.blockId || null;
            if (noteId) onnavigate(noteId, blkId);
        } else if (linkType === "note") {
            const noteId = linkEl.dataset.noteId;
            if (noteId) onnavigate(noteId, null);
        }
    }

    export function getContent(): string {
        return plainText;
    }

    /**
     * applyFormat — called by the top toolbar.
     */
    export function applyFormat(type: string) {
        if (!editorEl) return;

        if (!isFocused) {
            editorEl.focus();
            setTimeout(() => applyFormat(type), 30);
            return;
        }

        const sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        if (!editorEl.contains(range.commonAncestorContainer)) return;

        // ── Inline formats ─────────────────────────────────────────
        const inlineMap: Record<string, [string, string]> = {
            bold: ["**", "**"],
            italic: ["_", "_"],
            strike: ["~~", "~~"],
            code: ["`", "`"],
        };

        if (type in inlineMap) {
            const [open, close] = inlineMap[type];
            if (!range.collapsed) {
                const selected = range.toString();
                range.deleteContents();
                const tn = document.createTextNode(open + selected + close);
                range.insertNode(tn);
                range.setStartAfter(tn);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            } else {
                const placeholder = open + type + close;
                const tn = document.createTextNode(placeholder);
                range.insertNode(tn);
                range.setStartAfter(tn);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            }
            plainText = editorEl.innerText ?? "";
            onchange(blockId, plainText);
            return;
        }

        // ── Block-level formats ────────────────────────────────────
        const insertText = (text: string) => {
            const tn = document.createTextNode(text);
            range.deleteContents();
            range.insertNode(tn);
            range.setStartAfter(tn);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
            plainText = editorEl!.innerText ?? "";
            onchange(blockId, plainText);
        };

        if (type === "hr") {
            insertText("\n---\n");
            return;
        }
        if (type === "list") {
            insertText("\n- ");
            return;
        }
        if (type === "quote") {
            insertText("\n> ");
            return;
        }

        const headingMap: Record<string, string> = {
            h1: "\n# ",
            h2: "\n## ",
            h3: "\n### ",
        };
        if (type in headingMap) {
            insertText(headingMap[type]);
        }
    }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
    bind:this={editorEl}
    class="rich-text-block editor-block {className}"
    contenteditable="true"
    data-block-id={blockId}
    onfocus={handleFocus}
    onblur={handleBlur}
    oninput={handleInput}
    onmousedown={handleMouseDown}
></div>

<style>
    .rich-text-block {
        outline: none;
        min-height: 1.5em;
        color: #d4d4d4;
        caret-color: #f97316;
        line-height: 1.7;
        white-space: pre-wrap;
        word-break: break-word;
    }

    /* ── Rendered view-mode elements ─────────────────────────────── */
    :global(.rich-text-block .md-line) {
        display: block;
        min-height: 1.6em;
        line-height: 1.7;
        padding: 1px 0;
        white-space: pre-wrap;
        word-break: break-word;
    }

    :global(.rich-text-block h1, .rich-text-block .md-h1) {
        font-size: 1.85em;
        font-weight: 700;
        margin: 0;
        line-height: 1.3;
        color: #f0f0f0;
    }
    :global(.rich-text-block h2, .rich-text-block .md-h2) {
        font-size: 1.4em;
        font-weight: 600;
        margin: 0;
        line-height: 1.35;
        color: #ebebeb;
    }
    :global(.rich-text-block h3, .rich-text-block .md-h3) {
        font-size: 1.15em;
        font-weight: 600;
        margin: 0;
        line-height: 1.4;
        color: #e5e5e5;
    }
    :global(
            .rich-text-block h4,
            .rich-text-block .md-h4,
            .rich-text-block h5,
            .rich-text-block .md-h5,
            .rich-text-block h6,
            .rich-text-block .md-h6
        ) {
        font-weight: 600;
        margin: 0;
        color: #e0e0e0;
    }

    :global(.rich-text-block strong) {
        color: #f5f5f5;
        font-weight: 600;
    }
    :global(.rich-text-block em) {
        color: #c8c8c8;
        font-style: italic;
    }
    :global(.rich-text-block del) {
        color: #737373;
        text-decoration: line-through;
    }

    :global(.rich-text-block code) {
        background: rgba(255, 255, 255, 0.07);
        color: #e06c75;
        padding: 0px 5px;
        border-radius: 4px;
        font-family: "Fira Code", monospace;
        font-size: 0.875em;
    }
    :global(.rich-text-block pre) {
        background: #1e1e2e;
        border-radius: 8px;
        padding: 12px 16px;
        overflow-x: auto;
        margin: 4px 0;
        border: 1px solid #2e2e3e;
    }
    :global(.rich-text-block pre code) {
        background: none;
        padding: 0;
        color: #cdd6f4;
    }

    :global(.rich-text-block .md-bq) {
        display: block;
        border-left: 3px solid #f97316;
        padding: 2px 10px;
        color: #a0a0a0;
        font-style: italic;
        background: rgba(249, 115, 22, 0.05);
        border-radius: 0 4px 4px 0;
    }

    :global(.rich-text-block .md-li) {
        display: flex;
        gap: 8px;
        align-items: baseline;
    }
    :global(.rich-text-block .md-li-dot) {
        color: #f97316;
        font-weight: 700;
        flex-shrink: 0;
        min-width: 16px;
    }
    :global(.rich-text-block .md-li-text) {
        flex: 1;
    }

    :global(.rich-text-block .md-hr) {
        border: none;
        border-top: 1px solid #333;
        margin: 4px 0;
    }

    :global(.rich-text-block p) {
        margin: 0;
        line-height: 1.7;
    }
    :global(.rich-text-block ul, .rich-text-block ol) {
        padding-left: 1.5em;
        margin: 0;
    }
    :global(.rich-text-block li) {
        margin: 0;
    }
    :global(.rich-text-block blockquote) {
        border-left: 3px solid #f97316;
        margin: 0;
        padding: 4px 12px;
        color: #a0a0a0;
        font-style: italic;
        background: rgba(249, 115, 22, 0.05);
        border-radius: 0 4px 4px 0;
    }

    :global(.rich-text-block .note-link) {
        border-radius: 3px;
        padding: 0 2px;
        cursor: pointer;
        user-select: none;
        font-weight: 500;
        transition:
            background 0.15s,
            color 0.15s;
    }
    :global(.rich-text-block .note-link--note) {
        color: #f97316;
        border-bottom: 1px solid rgba(249, 115, 22, 0.4);
    }
    :global(.rich-text-block .note-link--note:hover) {
        background: rgba(249, 115, 22, 0.12);
        color: #fb923c;
    }
    :global(.rich-text-block .note-link--block) {
        color: #f59e0b;
        border-bottom: 1px dashed rgba(245, 158, 11, 0.5);
    }
    :global(.rich-text-block .note-link--block:hover) {
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
    }
    :global(.rich-text-block .note-link--web) {
        color: #38bdf8;
        border-bottom: 1px solid rgba(56, 189, 248, 0.35);
    }
    :global(.rich-text-block .note-link--web:hover) {
        background: rgba(56, 189, 248, 0.1);
        color: #7dd3fc;
    }

    :global(.rich-text-block .katex-display) {
        margin: 4px 0;
    }
    :global(.katex-error) {
        color: #e06c75;
        font-style: italic;
        font-size: 0.875em;
    }
</style>
