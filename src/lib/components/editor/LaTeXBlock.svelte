<script lang="ts">
    /**
     * LaTeXBlock.svelte
     * =================
     * Display-math block type ("latex").
     * View: renders $$...$$ with KaTeX in display mode.
     * Edit: plain <textarea> for raw LaTeX input.
     */
    import katex from "katex";

    interface Props {
        blockId: string;
        initialContent: string;
        onchange: (blockId: string, text: string) => void;
        className?: string;
    }

    let { blockId, initialContent, onchange, className = "" }: Props = $props();

    let rawLatex = $state(initialContent);
    let isEditing = $state(false);
    let renderedHtml = $state("");
    let textareaEl = $state<HTMLTextAreaElement | null>(null);

    function renderLatex(src: string): string {
        if (!src.trim())
            return '<span class="latex-placeholder">Click to enter LaTeX…</span>';
        try {
            return katex.renderToString(src, {
                displayMode: true,
                throwOnError: false,
                output: "html",
            });
        } catch {
            return `<span class="katex-error">$$${src}$$</span>`;
        }
    }

    $effect(() => {
        renderedHtml = renderLatex(rawLatex);
    });

    function enterEdit() {
        isEditing = true;
        // Focus textarea after DOM update
        setTimeout(() => textareaEl?.focus(), 0);
    }

    function exitEdit() {
        isEditing = false;
        renderedHtml = renderLatex(rawLatex);
        onchange(blockId, rawLatex);
    }

    function handleInput(e: Event) {
        rawLatex = (e.target as HTMLTextAreaElement).value;
        onchange(blockId, rawLatex);
    }

    function handleKeyDown(e: KeyboardEvent) {
        if (e.key === "Escape") {
            (e.target as HTMLElement).blur();
        }
    }

    /** Called by the top toolbar to switch to edit mode */
    export function enterEditMode() {
        if (!isEditing) enterEdit();
    }

    /**
     * Insert a LaTeX snippet at the current cursor position in the textarea.
     * If not in edit mode yet, enters edit mode first then inserts.
     */
    export function insertSnippet(text: string) {
        if (!isEditing) {
            enterEdit();
            // Wait for the textarea to mount
            setTimeout(() => insertSnippet(text), 30);
            return;
        }
        if (!textareaEl) return;
        const start = textareaEl.selectionStart ?? rawLatex.length;
        const end = textareaEl.selectionEnd ?? rawLatex.length;
        const before = rawLatex.slice(0, start);
        const after = rawLatex.slice(end);
        rawLatex = before + text + after;
        onchange(blockId, rawLatex);
        // Restore cursor inside the snippet (e.g. inside first {})
        const braceIdx = text.indexOf("{}");
        const cursorPos =
            braceIdx >= 0 ? start + braceIdx + 1 : start + text.length;
        setTimeout(() => {
            if (textareaEl) {
                textareaEl.selectionStart = cursorPos;
                textareaEl.selectionEnd = cursorPos;
                textareaEl.focus();
            }
        }, 0);
    }
</script>

<div class="latex-block editor-block {className}" data-block-id={blockId}>
    {#if isEditing}
        <div class="latex-edit">
            <div class="latex-edit-header">
                <span class="latex-label">LaTeX</span>
                <button class="latex-done-btn" onclick={exitEdit}>Done</button>
            </div>
            <textarea
                bind:this={textareaEl}
                class="latex-textarea"
                value={rawLatex}
                oninput={handleInput}
                onblur={exitEdit}
                onkeydown={handleKeyDown}
                placeholder="Enter LaTeX expression…"
                rows={Math.max(2, rawLatex.split("\n").length)}
            ></textarea>
            <!-- Live preview while editing -->
            <div class="latex-preview">
                {@html renderLatex(rawLatex)}
            </div>
        </div>
    {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class="latex-rendered"
            onclick={enterEdit}
            title="Click to edit LaTeX"
        >
            {@html renderedHtml}
        </div>
    {/if}
</div>

<style>
    .latex-block {
        position: relative;
        border-radius: 8px;
        transition: background 0.15s;
    }

    /* View mode */
    .latex-rendered {
        padding: 16px;
        text-align: center;
        cursor: pointer;
        border-radius: 8px;
        border: 1px solid transparent;
        transition:
            border-color 0.15s,
            background 0.15s;
    }
    .latex-rendered:hover {
        border-color: #404040;
        background: rgba(249, 115, 22, 0.04);
    }
    :global(.latex-rendered .katex-display) {
        margin: 0;
        color: #e8e8e8;
    }

    /* Edit mode */
    .latex-edit {
        border: 1px solid #f97316;
        border-radius: 8px;
        overflow: hidden;
    }
    .latex-edit-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 12px;
        background: rgba(249, 115, 22, 0.08);
        border-bottom: 1px solid rgba(249, 115, 22, 0.2);
    }
    .latex-label {
        font-size: 11px;
        font-weight: 600;
        color: #f97316;
        font-family: "Fira Code", monospace;
        letter-spacing: 0.05em;
    }
    .latex-done-btn {
        background: none;
        border: none;
        color: #f97316;
        font-size: 12px;
        cursor: pointer;
        padding: 2px 8px;
        border-radius: 4px;
        transition: background 0.15s;
    }
    .latex-done-btn:hover {
        background: rgba(249, 115, 22, 0.15);
    }
    .latex-textarea {
        width: 100%;
        background: #1a1a1a;
        color: #abb2bf;
        font-family: "Fira Code", "Fira Mono", monospace;
        font-size: 0.9em;
        padding: 10px 14px;
        outline: none;
        border: none;
        resize: vertical;
        box-sizing: border-box;
        white-space: pre;
        line-height: 1.6;
    }
    .latex-preview {
        padding: 12px 16px;
        text-align: center;
        border-top: 1px solid rgba(249, 115, 22, 0.15);
        min-height: 48px;
    }
    :global(.latex-preview .katex-display) {
        margin: 0;
        color: #e8e8e8;
    }
    .latex-placeholder {
        color: #555;
        font-style: italic;
        font-size: 0.9em;
    }
    :global(.katex-error) {
        color: #e06c75;
        font-style: italic;
        font-size: 0.9em;
    }
</style>
