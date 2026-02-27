<script lang="ts">
    /**
     * LinkedBlock.svelte
     * ==================
     * A rich-text block that renders [[display|note_id]] links inline.
     *
     * Behavior:
     * - Displays as styled text with links rendered as blue spans
     * - When the cursor keyboard-enters a link token, the raw [[...]] is revealed
     * - Clicking a link span dispatches a "navigate" event to the parent
     * - All edits go through the contenteditable div; we parse on blur/input
     */

    import { parseLinks, findLinkAtOffset } from "$lib/utils/linkParser";
    import type { Token } from "$lib/utils/linkParser";

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

    // Whether the cursor is currently inside a link token (for editing reveal)
    let cursorInLink = $state(false);

    // Tracks if we're in "edit mode" (focused) — switches rendering strategy
    let isFocused = $state(false);

    // On mount: set initial HTML
    $effect(() => {
        if (editorEl) {
            editorEl.innerHTML = buildDisplayHtml(initialContent);
        }
    });

    // ── Rendering ────────────────────────────────────────────────────────

    function buildDisplayHtml(text: string): string {
        const tokens: Token[] = parseLinks(text);
        return tokens
            .map((tok) => {
                if (tok.type === "text") {
                    // Escape HTML entities but preserve newlines
                    return tok.raw
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/\n/g, "<br>");
                } else {
                    // Resolve note title for tooltip
                    const note = notesList.find((n) => n.noteId === tok.noteId);
                    const title = note?.noteTitle ?? tok.display;
                    const target = tok.blockId
                        ? `${tok.noteId}/${tok.blockId}`
                        : tok.noteId;
                    return `<span
                        class="note-link"
                        data-note-id="${tok.noteId}"
                        data-block-id="${tok.blockId ?? ""}"
                        data-raw="${encodeURIComponent(tok.raw)}"
                        title="→ ${title}"
                        contenteditable="false"
                    >${tok.display}</span>`;
                }
            })
            .join("");
    }

    // ── Event Handlers ────────────────────────────────────────────────────

    function handleFocus() {
        isFocused = true;
        // Replace rendered HTML with raw text for editing
        if (editorEl) {
            const raw = plainText;
            editorEl.textContent = raw;
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
        // Re-render links after editing
        if (editorEl) {
            const newText = editorEl.textContent ?? "";
            plainText = newText;
            editorEl.innerHTML = buildDisplayHtml(newText);
            onchange(blockId, newText);
        }
    }

    function handleInput(e: Event) {
        // Keep our plainText in sync during editing
        const target = e.target as HTMLElement;
        plainText = target.textContent ?? "";
        onchange(blockId, plainText);
    }

    function handleKeyDown(e: KeyboardEvent) {
        if (e.key === "Enter" && !e.shiftKey) {
            // Let parent handle Enter to create new block
            // (when at the very end of the block)
        }
    }

    function handleClick(e: MouseEvent) {
        // Check if user clicked on a link span
        const target = e.target as HTMLElement;
        if (target.classList.contains("note-link")) {
            const noteId = target.dataset.noteId;
            const blkId = target.dataset.blockId || null;
            if (noteId) {
                e.preventDefault();
                e.stopPropagation();
                onnavigate(noteId, blkId ?? null);
            }
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
    onclick={handleClick}
></div>

<style>
    .linked-block {
        white-space: pre-wrap;
        word-break: break-word;
        outline: none;
        min-height: 1.5em;
        line-height: 1.7;
    }

    /* Link chip rendered in display mode */
    :global(.linked-block .note-link) {
        color: #f97316; /* orange-500 — matches app accent */
        border-bottom: 1px solid rgba(249, 115, 22, 0.4);
        cursor: pointer;
        border-radius: 2px;
        padding: 0 1px;
        transition:
            background 0.15s,
            color 0.15s;
        user-select: none;
    }

    :global(.linked-block .note-link:hover) {
        background: rgba(249, 115, 22, 0.12);
        color: #fb923c; /* orange-400 */
        border-bottom-color: #f97316;
    }
</style>
