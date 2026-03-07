<script lang="ts">
    /**
     * RichTextBlock.svelte — Obsidian-style live preview
     * ====================================================
     * VIEW (not focused): full marked + KaTeX + links via renderViewHtml()
     * EDIT (focused):     line-by-line live preview
     *   • Active line (cursor on it) → raw markdown text
     *   • Every other line           → renderLineHtml() (rendered)
     *
     * Line structure in edit mode:
     *   <div class="md-line" data-raw="...encoded raw...">rendered HTML</div>
     *                    ↑ rendered/inactive
     *   <div class="md-line md-line-active">raw text here</div>
     *                    ↑ active/editable
     *
     * Cursor tracking: document selectionchange → find which .md-line div
     * contains the anchor → if different from previous, swap rendering.
     *
     * Enter: intercepted to reliably split the active line.
     * Backspace at col 0: intercepted to merge with previous line.
     */

    import {
        renderViewHtml,
        renderLineHtml,
        escapeHtml,
    } from "$lib/utils/markdownRenderer";
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
    let activeLine = $state<HTMLElement | null>(null); // the active .md-line div
    let rebuilding = false; // guard: suppress selectionchange during DOM manipulation

    // ── DOM helpers ────────────────────────────────────────────────────────

    /** Get all .md-line divs */
    function lineEls(): HTMLElement[] {
        if (!editorEl) return [];
        return Array.from(
            editorEl.querySelectorAll(".md-line"),
        ) as HTMLElement[];
    }

    /** Reconstruct raw plainText from current .md-line DOM */
    function getRawText(): string {
        return lineEls()
            .map((el) => {
                const enc = el.dataset.raw;
                if (enc !== undefined) return decodeURIComponent(enc); // rendered line
                return el.textContent ?? ""; // active (raw) line
            })
            .join("\n");
    }

    /** Place cursor at end of a line element */
    function cursorAtEnd(lineEl: HTMLElement) {
        const sel = window.getSelection();
        if (!sel) return;
        const range = document.createRange();
        if (lineEl.lastChild && lineEl.lastChild.nodeType === Node.TEXT_NODE) {
            const tn = lineEl.lastChild as Text;
            range.setStart(tn, tn.length);
        } else {
            range.selectNodeContents(lineEl);
            range.collapse(false);
        }
        sel.removeAllRanges();
        sel.addRange(range);
    }

    /** Place cursor at a given char offset in a text-only line element */
    function cursorAt(lineEl: HTMLElement, offset: number) {
        const sel = window.getSelection();
        if (!sel) return;
        const range = document.createRange();
        const tn = lineEl.firstChild;
        if (tn && tn.nodeType === Node.TEXT_NODE) {
            const clamped = Math.min(offset, (tn as Text).length);
            range.setStart(tn, clamped);
        } else {
            range.selectNodeContents(lineEl);
            range.collapse(false);
        }
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
    }

    /** Find which .md-line div contains the current selection anchor */
    function findActiveLine(): HTMLElement | null {
        if (!editorEl) return null;
        const sel = window.getSelection();
        if (!sel || !sel.rangeCount) return null;
        const node = sel.anchorNode;
        for (const el of lineEls()) {
            if (el === node || el.contains(node)) return el;
        }
        return null;
    }

    // ── Rendering ──────────────────────────────────────────────────────────

    /** Render a line div as inactive (use renderLineHtml) */
    function renderLineEl(el: HTMLElement, raw: string) {
        el.innerHTML = renderLineHtml(raw, notesList);
        el.dataset.raw = encodeURIComponent(raw);
        el.classList.remove("md-line-active");
    }

    /** Make a line div the active (raw) editing line */
    function activateLineEl(
        el: HTMLElement,
        raw: string,
        cursorOffset?: number,
    ) {
        el.textContent = raw;
        delete el.dataset.raw;
        el.classList.add("md-line-active");
        if (cursorOffset !== undefined) {
            cursorAt(el, cursorOffset);
        } else {
            cursorAtEnd(el);
        }
    }

    /** Build full edit-mode HTML from raw lines, with activeIdx as the editing line */
    function buildEditHtml(rawLines: string[], activeIdx: number): string {
        return rawLines
            .map((line, i) => {
                if (i === activeIdx) {
                    return `<div class="md-line md-line-active">${escapeHtml(line)}</div>`;
                }
                const inner = renderLineHtml(line, notesList);
                return `<div class="md-line" data-raw="${encodeURIComponent(line)}">${inner}</div>`;
            })
            .join("");
    }

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

        rebuilding = true;
        const rawLines = plainText.split("\n");
        // Activate the last line by default (cursor goes there on focus)
        editorEl.innerHTML = buildEditHtml(rawLines, rawLines.length - 1);
        const els = lineEls();
        const lastEl = els[els.length - 1] ?? null;
        activeLine = lastEl;
        if (lastEl) cursorAtEnd(lastEl);
        rebuilding = false;

        document.addEventListener("selectionchange", handleSelectionChange);
    }

    function handleBlur() {
        document.removeEventListener("selectionchange", handleSelectionChange);
        isFocused = false;
        activeLine = null;
        if (!editorEl) return;
        const raw = getRawText();
        plainText = raw;
        onchange(blockId, raw);
        editorEl.innerHTML = renderViewHtml(raw, notesList);
    }

    function handleSelectionChange() {
        if (!isFocused || rebuilding || !editorEl) return;

        const newActive = findActiveLine();
        if (!newActive || newActive === activeLine) return;

        rebuilding = true;

        // Determine movement direction to place cursor correctly
        const els = lineEls();
        const oldIdx = activeLine ? els.indexOf(activeLine) : -1;
        const newIdx = els.indexOf(newActive);
        // Moving forward (right/down): cursor at START of new line
        // Moving backward (left/up) or first activation: cursor at END
        const cursorOffset = oldIdx >= 0 && newIdx > oldIdx ? 0 : undefined;

        // Render the old active line
        if (activeLine) {
            const oldRaw = activeLine.textContent ?? "";
            renderLineEl(activeLine, oldRaw);
        }

        // Activate the new line
        const enc = newActive.dataset.raw;
        const raw =
            enc !== undefined
                ? decodeURIComponent(enc)
                : (newActive.textContent ?? "");
        activateLineEl(newActive, raw, cursorOffset);
        activeLine = newActive;

        // Update plainText
        plainText = getRawText();
        onchange(blockId, plainText);

        rebuilding = false;
    }

    function handleInput() {
        if (rebuilding) return;
        plainText = getRawText();
        onchange(blockId, plainText);
    }

    function handleKeyDown(e: KeyboardEvent) {
        if (e.key === "Enter") {
            e.preventDefault();
            handleEnter();
        } else if (e.key === "Backspace") {
            const sel = window.getSelection();
            if (sel?.rangeCount && sel.getRangeAt(0).startOffset === 0) {
                e.preventDefault();
                handleBackspaceAtLineStart();
            }
        }
    }

    function handleEnter() {
        if (!activeLine || !editorEl) return;

        rebuilding = true;
        const sel = window.getSelection();
        const offset = sel?.rangeCount
            ? sel.getRangeAt(0).startOffset
            : (activeLine.textContent?.length ?? 0);
        const currentText = activeLine.textContent ?? "";
        const before = currentText.slice(0, offset);
        const after = currentText.slice(offset);

        // Render the before-part
        activeLine.textContent = before;
        renderLineEl(activeLine, before);

        // Create new active line with after-part
        const newEl = document.createElement("div");
        newEl.className = "md-line md-line-active";
        newEl.textContent = after;
        activeLine.after(newEl);

        activeLine = newEl;
        cursorAt(newEl, 0);

        plainText = getRawText();
        onchange(blockId, plainText);
        rebuilding = false;
    }

    function handleBackspaceAtLineStart() {
        if (!activeLine || !editorEl) return;
        const els = lineEls();
        const idx = els.indexOf(activeLine);
        if (idx <= 0) return; // Already at first line

        rebuilding = true;
        const prevEl = els[idx - 1];
        const prevRaw =
            prevEl.dataset.raw !== undefined
                ? decodeURIComponent(prevEl.dataset.raw)
                : (prevEl.textContent ?? "");
        const currentRaw = activeLine.textContent ?? "";
        const mergedRaw = prevRaw + currentRaw;
        const cursorPos = prevRaw.length;

        activeLine.remove();
        prevEl.removeAttribute("data-raw");
        prevEl.classList.add("md-line-active");
        prevEl.textContent = mergedRaw;
        activeLine = prevEl;
        cursorAt(prevEl, cursorPos);

        plainText = getRawText();
        onchange(blockId, plainText);
        rebuilding = false;
    }

    function handleMouseDown(e: MouseEvent) {
        const target = e.target as HTMLElement;
        const linkEl = target.closest(".note-link") as HTMLElement | null;
        if (!linkEl) return;

        // In view mode only — links don't exist in edit-mode DOM
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
     * type: 'bold' | 'italic' | 'strike' | 'code' | 'list' | 'quote' | 'hr' | 'h1' | 'h2' | 'h3'
     */
    export function applyFormat(type: string) {
        if (!editorEl) return;

        // If not focused yet, focus first so activeLine is set
        if (!isFocused) {
            editorEl.focus();
            // Give focus handler time to run, then retry
            setTimeout(() => applyFormat(type), 30);
            return;
        }

        // ── Inline formats ─────────────────────────────────────────
        const inlineMap: Record<string, [string, string]> = {
            bold: ["**", "**"],
            italic: ["_", "_"],
            strike: ["~~", "~~"],
            code: ["`", "`"],
        };

        if (type in inlineMap) {
            const [open, close] = inlineMap[type];
            const sel = window.getSelection();

            // Only act if the selection is inside our editor
            if (sel && sel.rangeCount > 0 && activeLine) {
                const range = sel.getRangeAt(0);
                const inEditor = editorEl.contains(
                    range.commonAncestorContainer,
                );

                if (inEditor && !range.collapsed) {
                    // Wrap the selected text
                    const selected = range.toString();
                    const wrapped = open + selected + close;
                    range.deleteContents();
                    const textNode = document.createTextNode(wrapped);
                    range.insertNode(textNode);
                    // Move cursor after the inserted text
                    range.setStartAfter(textNode);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                } else if (activeLine) {
                    // No selection — insert placeholder at cursor end
                    const placeholder =
                        open +
                        (type === "bold"
                            ? "bold"
                            : type === "italic"
                              ? "italic"
                              : type === "strike"
                                ? "strikethrough"
                                : "code") +
                        close;
                    const currentText = activeLine.textContent ?? "";
                    const curSel = window.getSelection();
                    const offset = curSel?.rangeCount
                        ? curSel.getRangeAt(0).startOffset
                        : currentText.length;
                    const newText =
                        currentText.slice(0, offset) +
                        placeholder +
                        currentText.slice(offset);
                    activeLine.textContent = newText;
                    // Place cursor after the inserted syntax
                    cursorAt(activeLine, offset + placeholder.length);
                }
            } else if (activeLine) {
                // No selection at all — insert at end
                const placeholder =
                    open +
                    (type === "bold"
                        ? "bold"
                        : type === "italic"
                          ? "italic"
                          : type === "strike"
                            ? "strikethrough"
                            : "code") +
                    close;
                activeLine.textContent =
                    (activeLine.textContent ?? "") + placeholder;
                cursorAtEnd(activeLine);
            }

            plainText = getRawText();
            onchange(blockId, plainText);
            return;
        }

        // ── Block-level formats ────────────────────────────────────
        if (type === "hr") {
            // Insert a '---' on a new line after the active line
            if (!activeLine || !editorEl) return;
            rebuilding = true;
            const currentRaw = activeLine.textContent ?? "";
            renderLineEl(activeLine, currentRaw);

            const hrEl = document.createElement("div");
            hrEl.className = "md-line md-line-active";
            hrEl.textContent = "---";
            activeLine.after(hrEl);

            activeLine = hrEl;
            cursorAtEnd(hrEl);
            plainText = getRawText();
            onchange(blockId, plainText);
            rebuilding = false;
            return;
        }

        if (type === "list") {
            if (!activeLine) return;
            rebuilding = true;
            const raw = activeLine.textContent ?? "";
            // If line is empty, just prepend '- '
            if (raw.trim() === "") {
                activeLine.textContent = "- ";
                cursorAtEnd(activeLine);
            } else {
                // Render the current line, create new '- ' line after it
                renderLineEl(activeLine, raw);
                const newEl = document.createElement("div");
                newEl.className = "md-line md-line-active";
                newEl.textContent = "- ";
                activeLine.after(newEl);
                activeLine = newEl;
                cursorAtEnd(newEl);
            }
            plainText = getRawText();
            onchange(blockId, plainText);
            rebuilding = false;
            return;
        }

        if (type === "quote") {
            if (!activeLine) return;
            rebuilding = true;
            const raw = activeLine.textContent ?? "";
            if (raw.trim() === "") {
                activeLine.textContent = "> ";
                cursorAtEnd(activeLine);
            } else {
                renderLineEl(activeLine, raw);
                const newEl = document.createElement("div");
                newEl.className = "md-line md-line-active";
                newEl.textContent = "> ";
                activeLine.after(newEl);
                activeLine = newEl;
                cursorAtEnd(newEl);
            }
            plainText = getRawText();
            onchange(blockId, plainText);
            rebuilding = false;
            return;
        }

        // Headings: h1, h2, h3 — toggle/cycle on the active line
        const headingMap: Record<string, string> = {
            h1: "# ",
            h2: "## ",
            h3: "### ",
        };
        if (type in headingMap) {
            if (!activeLine) return;
            rebuilding = true;
            let raw = activeLine.textContent ?? "";
            // Remove any existing heading prefix first
            raw = raw.replace(/^#{1,6}\s/, "");
            const prefix = headingMap[type];
            activeLine.textContent = prefix + raw;
            cursorAtEnd(activeLine);
            plainText = getRawText();
            onchange(blockId, plainText);
            rebuilding = false;
            return;
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
    onkeydown={handleKeyDown}
    onmousedown={handleMouseDown}
></div>

<style>
    .rich-text-block {
        outline: none;
        min-height: 1.5em;
        color: #d4d4d4;
        caret-color: #f97316;
    }

    /* Each line is a block div */
    :global(.rich-text-block .md-line) {
        display: block;
        min-height: 1.6em;
        line-height: 1.7;
        padding: 1px 0;
        white-space: pre-wrap;
        word-break: break-word;
    }

    /* Active line: raw text, slightly highlighted */
    :global(.rich-text-block .md-line-active) {
        background: rgba(249, 115, 22, 0.04);
        border-radius: 3px;
    }

    /* ── Rendered line elements ─────────────────────────────────── */
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

    /* Blockquote (inline span, not block element) */
    :global(.rich-text-block .md-bq) {
        display: block;
        border-left: 3px solid #f97316;
        padding: 2px 10px;
        color: #a0a0a0;
        font-style: italic;
        background: rgba(249, 115, 22, 0.05);
        border-radius: 0 4px 4px 0;
    }

    /* List items */
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

    /* View-mode (full block render) elements */
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

    /* Links */
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

    /* KaTeX */
    :global(.rich-text-block .katex-display) {
        margin: 4px 0;
    }
    :global(.katex-error) {
        color: #e06c75;
        font-style: italic;
        font-size: 0.875em;
    }
</style>
