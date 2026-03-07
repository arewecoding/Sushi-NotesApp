<script lang="ts">
    /**
     * LinkedBlock.svelte
     * ==================
     * A rich-text block that renders inline links:
     *   [[text||note||uuid]]   → orange span, navigates to note
     *   [[text||block||nid/bid]] → amber span, navigates to note + scrolls block
     *   [[text||web||url]]     → sky-blue span, opens URL in default browser
     *   [[text|uuid]]          → legacy fallback, treated as note link
     *
     * Editing:
     *   - Click on a link  → navigates / opens URL  (never enters edit mode)
     *   - Click elsewhere → contenteditable focus, raw [[...]] text revealed
     *   - Keyboard cursor → naturally editable in focused state
     */

    import { parseLinks } from "$lib/utils/linkParser";
    import type { Token } from "$lib/utils/linkParser";
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

    // The contenteditable div reference
    let editorEl = $state<HTMLElement | null>(null);

    // Current plain-text content (source of truth for saving)
    let plainText = $state(initialContent);

    // Whether the block is actively being edited
    let isFocused = $state(false);

    // On mount / when editorEl binds — render display HTML
    $effect(() => {
        const el = editorEl;
        if (el && !isFocused) {
            el.innerHTML = buildDisplayHtml(plainText);
        }
    });

    // Re-render when notesList updates (async load) so tooltip titles are current
    $effect(() => {
        const _list = notesList; // reactive dependency
        const el = editorEl;
        if (el && !isFocused) {
            el.innerHTML = buildDisplayHtml(plainText);
        }
    });

    // ── Rendering ────────────────────────────────────────────────────────────

    function escapeHtml(s: string): string {
        return s
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\n/g, "<br>");
    }

    function buildDisplayHtml(text: string): string {
        const tokens: Token[] = parseLinks(text);
        return tokens
            .map((tok) => {
                if (tok.type === "text") return escapeHtml(tok.raw);

                // Resolve title for tooltip
                const noteTitle = tok.noteId
                    ? (notesList.find((n) => n.noteId === tok.noteId)
                          ?.noteTitle ?? tok.display)
                    : tok.display;

                if (tok.linkType === "note") {
                    return `<span
                        class="note-link note-link--note"
                        data-link-type="note"
                        data-note-id="${tok.noteId ?? ""}"
                        data-raw="${encodeURIComponent(tok.raw)}"
                        title="→ ${noteTitle}"
                        contenteditable="false"
                    >${tok.display}</span>`;
                }

                if (tok.linkType === "block") {
                    return `<span
                        class="note-link note-link--block"
                        data-link-type="block"
                        data-note-id="${tok.noteId ?? ""}"
                        data-block-id="${tok.blockId ?? ""}"
                        data-raw="${encodeURIComponent(tok.raw)}"
                        title="⚓ ${noteTitle} › block"
                        contenteditable="false"
                    >${tok.display}</span>`;
                }

                // web
                return `<span
                    class="note-link note-link--web"
                    data-link-type="web"
                    data-url="${encodeURIComponent(tok.url ?? "")}"
                    data-raw="${encodeURIComponent(tok.raw)}"
                    title="↗ ${tok.url}"
                    contenteditable="false"
                >${tok.display} ↗</span>`;
            })
            .join("");
    }

    // ── Event Handlers ────────────────────────────────────────────────────────

    function handleFocus() {
        isFocused = true;
        if (editorEl) {
            editorEl.textContent = plainText;
            // Move caret to end
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(editorEl);
            range.collapse(false);
            sel?.removeAllRanges();
            sel?.addRange(range);
        }
    }

    function handleBlur() {
        isFocused = false;
        if (editorEl) {
            const newText = editorEl.textContent ?? "";
            plainText = newText;
            editorEl.innerHTML = buildDisplayHtml(newText);
            onchange(blockId, newText);
        }
    }

    function handleInput(e: Event) {
        const target = e.target as HTMLElement;
        plainText = target.textContent ?? "";
        onchange(blockId, plainText);
    }

    function handleKeyDown(_e: KeyboardEvent) {
        // Parent handles Enter, etc.
    }

    function handleMouseDown(e: MouseEvent) {
        // MUST be mousedown — focus fires before click and destroys the spans.
        const target = e.target as HTMLElement;
        if (!target.classList.contains("note-link")) return;

        // Prevent focus (stay in display mode)
        e.preventDefault();

        const linkType = target.dataset.linkType;

        if (linkType === "web") {
            const url = decodeURIComponent(target.dataset.url ?? "");
            if (url) openUrl(url).catch(console.error);
            return;
        }

        if (linkType === "note") {
            const noteId = target.dataset.noteId;
            if (noteId) onnavigate(noteId, null);
            return;
        }

        if (linkType === "block") {
            const noteId = target.dataset.noteId;
            const blkId = target.dataset.blockId || null;
            if (noteId) onnavigate(noteId, blkId);
            return;
        }
    }

    // Public getter for current plain text (called by parent when saving)
    export function getContent(): string {
        return plainText;
    }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
    bind:this={editorEl}
    class="editor-block linked-block {className}"
    contenteditable="true"
    data-block-id={blockId}
    onfocus={handleFocus}
    onblur={handleBlur}
    oninput={handleInput}
    onkeydown={handleKeyDown}
    onmousedown={handleMouseDown}
></div>

<style>
    .linked-block {
        white-space: pre-wrap;
        word-break: break-word;
        outline: none;
        min-height: 1.5em;
        line-height: 1.7;
    }

    /* ── Base chip styles ─────────────────────────────────────── */
    :global(.linked-block .note-link) {
        border-radius: 3px;
        padding: 0 2px;
        cursor: pointer;
        user-select: none;
        font-weight: 500;
        transition:
            background 0.15s,
            color 0.15s,
            border-color 0.15s;
    }

    /* Note link — orange (existing accent) */
    :global(.linked-block .note-link--note) {
        color: #f97316;
        border-bottom: 1px solid rgba(249, 115, 22, 0.4);
    }
    :global(.linked-block .note-link--note:hover) {
        background: rgba(249, 115, 22, 0.12);
        color: #fb923c;
        border-bottom-color: #f97316;
    }

    /* Block link — amber */
    :global(.linked-block .note-link--block) {
        color: #f59e0b;
        border-bottom: 1px dashed rgba(245, 158, 11, 0.5);
    }
    :global(.linked-block .note-link--block:hover) {
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
        border-bottom-color: #f59e0b;
    }

    /* Web link — sky blue */
    :global(.linked-block .note-link--web) {
        color: #38bdf8;
        border-bottom: 1px solid rgba(56, 189, 248, 0.35);
    }
    :global(.linked-block .note-link--web:hover) {
        background: rgba(56, 189, 248, 0.1);
        color: #7dd3fc;
        border-bottom-color: #38bdf8;
    }
</style>
