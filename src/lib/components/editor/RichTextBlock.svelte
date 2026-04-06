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
        onlinkstart?: (blockId: string) => void;
        className?: string;
    }

    let {
        blockId,
        initialContent,
        notesList,
        onchange,
        onnavigate,
        onlinkstart,
        className = "",
    }: Props = $props();

    let editorEl = $state<HTMLElement | null>(null);
    let plainText = $state(initialContent);
    let isFocused = $state(false);

    /** Saved cursor/selection offsets for link insertion after modal closes */
    let savedCursorOffset = $state(-1);
    let savedSelectionStart = $state(-1);
    let savedSelectionEnd = $state(-1);

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

    // ── Helpers ────────────────────────────────────────────────────────────

    /**
     * Walk child <div> elements to build a newline-separated string.
     * This avoids the issue where innerText double-counts <br> inside
     * empty <div> elements, causing blank lines to multiply each blur.
     */
    function extractText(container: HTMLElement): string {
        const divs = container.querySelectorAll(":scope > div");
        if (divs.length === 0) {
            // Fallback: no child divs (e.g. single-line content)
            return container.textContent ?? "";
        }
        return Array.from(divs)
            .map((div) => {
                // An empty line is represented as <div><br></div>;
                // its textContent is "\n", so we trim that to "".
                const txt = div.textContent ?? "";
                return txt === "\n" ? "" : txt;
            })
            .join("\n");
    }

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
        const raw = extractText(editorEl);
        plainText = raw;
        onchange(blockId, raw);
        editorEl.innerHTML = renderViewHtml(raw, notesList);
    }

    function handleInput() {
        if (!editorEl) return;
        plainText = extractText(editorEl);
        onchange(blockId, plainText);
    }

    /**
     * Paste handler — intercept paste and insert only plain text.
     * Prevents HTML from being pasted into the contenteditable.
     */
    function handlePaste(e: ClipboardEvent) {
        e.preventDefault();
        const text = e.clipboardData?.getData("text/plain") ?? "";
        if (!text) return;

        const sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;

        const range = sel.getRangeAt(0);
        range.deleteContents();

        // Insert plain text, handling newlines by splitting into divs
        const lines = text.split("\n");
        const frag = document.createDocumentFragment();

        for (let i = 0; i < lines.length; i++) {
            if (i === 0) {
                // First line: just insert text at cursor
                frag.appendChild(document.createTextNode(lines[i]));
            } else {
                // Subsequent lines: create new div elements
                const div = document.createElement("div");
                div.textContent = lines[i] || "";
                if (!lines[i]) div.appendChild(document.createElement("br"));
                frag.appendChild(div);
            }
        }

        range.insertNode(frag);

        // Move cursor to end of inserted content
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);

        // Sync state
        if (editorEl) {
            plainText = extractText(editorEl);
            onchange(blockId, plainText);
        }
    }

    /**
     * Copy handler — ensure only plain text is copied (no HTML).
     */
    function handleCopy(e: ClipboardEvent) {
        e.preventDefault();
        const sel = window.getSelection();
        const text = sel?.toString() ?? "";
        e.clipboardData?.setData("text/plain", text);
    }

    /**
     * Cut handler — copy plain text then delete selection.
     */
    function handleCut(e: ClipboardEvent) {
        e.preventDefault();
        const sel = window.getSelection();
        const text = sel?.toString() ?? "";
        e.clipboardData?.setData("text/plain", text);

        // Delete the selected content
        if (sel && sel.rangeCount) {
            const range = sel.getRangeAt(0);
            range.deleteContents();
        }

        // Sync state
        if (editorEl) {
            plainText = extractText(editorEl);
            onchange(blockId, plainText);
        }
    }

    /**
     * Intercept the second `[` keypress to trigger the link modal.
     * Issue 1: prevent default so `[[` never appears in the text.
     */
    function handleKeydown(e: KeyboardEvent) {
        // ── Tab indent / Shift+Tab outdent ────────────────────────────
        if (isFocused && editorEl && e.key === "Tab") {
            e.preventDefault();

            const sel = window.getSelection();
            if (!sel || !sel.rangeCount) return;
            const range = sel.getRangeAt(0);

            if (e.shiftKey) {
                // Outdent: remove up to 4 leading spaces from the current line div
                const lineDiv = range.startContainer.nodeType === Node.TEXT_NODE
                    ? range.startContainer.parentElement
                    : range.startContainer;
                if (lineDiv && lineDiv !== editorEl) {
                    const text = lineDiv.textContent ?? "";
                    const stripped = text.replace(/^ {1,4}/, "");
                    if (stripped !== text) {
                        const removed = text.length - stripped.length;
                        lineDiv.textContent = stripped;
                        // Restore cursor
                        const newOffset = Math.max(0, range.startOffset - removed);
                        const textNode = lineDiv.firstChild;
                        if (textNode) {
                            const r = document.createRange();
                            r.setStart(textNode, Math.min(newOffset, textNode.textContent?.length ?? 0));
                            r.collapse(true);
                            sel.removeAllRanges();
                            sel.addRange(r);
                        }
                    }
                }
            } else {
                // Indent: insert 4 spaces at cursor
                const tn = document.createTextNode("    ");
                range.deleteContents();
                range.insertNode(tn);
                range.setStartAfter(tn);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            }

            plainText = extractText(editorEl);
            onchange(blockId, plainText);
            return;
        }

        // ── Keyboard shortcuts for inline formatting (Bug 3) ─────────
        if (isFocused && editorEl && (e.ctrlKey || e.metaKey)) {
            if (e.key === "b" || e.key === "B") {
                e.preventDefault();
                applyFormat("bold");
                return;
            }
            if (e.key === "i" || e.key === "I") {
                e.preventDefault();
                applyFormat("italic");
                return;
            }
        }

        // ── Link trigger: [[ ──────────────────────────────────────────
        if (e.key !== "[" || !isFocused || !editorEl || !onlinkstart) return;

        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) return;

        const range = sel.getRangeAt(0);
        const container = range.startContainer;

        // Check if the character immediately before the cursor is `[`
        if (container.nodeType === Node.TEXT_NODE) {
            const text = container.textContent ?? "";
            const offset = range.startOffset;
            if (offset > 0 && text[offset - 1] === "[") {
                // Prevent the second `[` from being inserted
                e.preventDefault();

                // Remove the first `[` that was already typed
                const before = text.slice(0, offset - 1);
                const after = text.slice(offset);
                container.textContent = before + after;

                // Restore cursor position
                const newRange = document.createRange();
                newRange.setStart(container, before.length);
                newRange.collapse(true);
                sel.removeAllRanges();
                sel.addRange(newRange);

                // Sync text state
                plainText = extractText(editorEl);
                onchange(blockId, plainText);

                // Save cursor offset in plainText for later insertion
                savedCursorOffset = computeTextOffset(editorEl);
                savedSelectionStart = -1;
                savedSelectionEnd = -1;

                // Open the link modal
                onlinkstart(blockId);
            }
        }
    }

    /**
     * Compute the plain-text offset of the cursor within the editor.
     * Walks child divs to find which character position the caret maps to.
     */
    function computeTextOffset(root: HTMLElement): number {
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) return plainText.length;

        const range = sel.getRangeAt(0);
        // Create a range from start of editor to cursor
        const preRange = document.createRange();
        preRange.selectNodeContents(root);
        preRange.setEnd(range.startContainer, range.startOffset);

        // The textContent of that range gives us the offset
        const textBeforeCursor = preRange.toString();
        return textBeforeCursor.length;
    }

    /**
     * Compute start and end plain-text offsets of the selection.
     */
    function computeSelectionOffsets(root: HTMLElement): { start: number; end: number } {
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) return { start: -1, end: -1 };

        const range = sel.getRangeAt(0);

        const startRange = document.createRange();
        startRange.selectNodeContents(root);
        startRange.setEnd(range.startContainer, range.startOffset);
        const start = startRange.toString().length;

        const endRange = document.createRange();
        endRange.selectNodeContents(root);
        endRange.setEnd(range.endContainer, range.endOffset);
        const end = endRange.toString().length;

        return { start, end };
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
     * Insert a link syntax string at the saved cursor position.
     * By the time this is called, the editor has blurred (modal stole focus),
     * so we splice into plainText at the saved offset instead of using DOM ranges.
     */
    export function insertLinkSyntax(syntax: string) {
        if (savedCursorOffset >= 0 && savedCursorOffset <= plainText.length) {
            plainText =
                plainText.slice(0, savedCursorOffset) +
                syntax +
                plainText.slice(savedCursorOffset);
        } else {
            // Fallback: append
            plainText += syntax;
        }
        savedCursorOffset = -1;
        onchange(blockId, plainText);
        // Re-render view mode
        if (editorEl && !isFocused) {
            editorEl.innerHTML = renderViewHtml(plainText, notesList);
        }
    }

    /**
     * Replace a saved text selection range with a link syntax string.
     * Used by the toolbar Link button flow (Issue 4).
     */
    export function replaceSelectionWithLink(syntax: string) {
        if (savedSelectionStart >= 0 && savedSelectionEnd >= savedSelectionStart) {
            plainText =
                plainText.slice(0, savedSelectionStart) +
                syntax +
                plainText.slice(savedSelectionEnd);
        } else {
            // Fallback: just insert at cursor
            insertLinkSyntax(syntax);
            return;
        }
        savedSelectionStart = -1;
        savedSelectionEnd = -1;
        onchange(blockId, plainText);
        if (editorEl && !isFocused) {
            editorEl.innerHTML = renderViewHtml(plainText, notesList);
        }
    }

    /**
     * Get the currently selected text and save the selection offsets.
     */
    export function getSelectedText(): string {
        if (!editorEl || !isFocused) return "";
        const sel = window.getSelection();
        if (!sel) return "";
        const text = sel.toString();

        // Save offsets for later insertion
        if (text) {
            const offsets = computeSelectionOffsets(editorEl);
            savedSelectionStart = offsets.start;
            savedSelectionEnd = offsets.end;
            savedCursorOffset = offsets.start;
        } else {
            savedCursorOffset = computeTextOffset(editorEl);
            savedSelectionStart = -1;
            savedSelectionEnd = -1;
        }

        return text;
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
    onkeydown={handleKeydown}
    onmousedown={handleMouseDown}
    onpaste={handlePaste}
    oncopy={handleCopy}
    oncut={handleCut}
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
        margin-bottom: 2px;
        white-space: pre-wrap;
        word-break: break-word;
    }
    /* Consecutive empty lines should not stack up huge gaps */
    :global(.rich-text-block .md-line:has(> br:only-child)) {
        margin-bottom: 0;
    }

    /* ── Indent guide lines ─────────────────────────────────── */
    :global(.rich-text-block .md-line.md-indented) {
        position: relative;
        padding-left: var(--indent-px);
    }
    :global(.rich-text-block .md-indent-guide) {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 1px;
        background: rgba(255, 255, 255, 0.06);
        pointer-events: none;
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
        color: #fbbf24;
        font-weight: 700;
        background: rgba(251, 191, 36, 0.08);
        padding: 0 2px;
        border-radius: 2px;
    }
    :global(.rich-text-block em) {
        color: #a78bfa;
        font-style: italic;
        background: rgba(167, 139, 250, 0.06);
        padding: 0 2px;
        border-radius: 2px;
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

    /* ── Fenced code blocks (``` ... ```) rendered in text blocks ─── */
    :global(.rich-text-block .md-code-fence) {
        position: relative;
        margin: 6px 0;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #262626;
        background: #171717;
    }
    :global(.rich-text-block .md-code-fence pre) {
        margin: 0;
        border: none;
        border-radius: 0;
        background: #171717;
        padding: 12px 16px;
    }
    :global(.rich-text-block .md-code-fence code) {
        background: none;
        padding: 0;
        color: #cdd6f4;
        font-family: "Fira Code", "Cascadia Code", monospace;
        font-size: 13px;
        line-height: 1.6;
    }
    :global(.rich-text-block .md-code-fence-lang) {
        display: inline-block;
        position: absolute;
        top: 4px;
        right: 8px;
        font-size: 10px;
        color: #525252;
        font-family: inherit;
        text-transform: lowercase;
        letter-spacing: 0.5px;
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
