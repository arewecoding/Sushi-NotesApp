<script lang="ts">
    /**
     * CodeBlock.svelte — CodeMirror 6 powered code editor block
     * ==========================================================
     * Replaces the old <pre contenteditable> with a full-featured
     * code editor: syntax highlighting, line numbers, Tab indent,
     * bracket matching, copy button, collapse toggle, language
     * selector, and paste-based auto-detection.
     */
    import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection } from "@codemirror/view";
    import { EditorState, Compartment } from "@codemirror/state";
    import { indentWithTab } from "@codemirror/commands";
    import { indentUnit, indentOnInput, bracketMatching, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
    import { closeBrackets } from "@codemirror/autocomplete";
    import { history, historyKeymap } from "@codemirror/commands";
    import { defaultKeymap } from "@codemirror/commands";
    import { tags } from "@lezer/highlight";

    // Language imports
    import { python } from "@codemirror/lang-python";
    import { javascript } from "@codemirror/lang-javascript";
    import { sql } from "@codemirror/lang-sql";
    import { rust } from "@codemirror/lang-rust";
    import { go } from "@codemirror/lang-go";
    import { html } from "@codemirror/lang-html";
    import { css } from "@codemirror/lang-css";

    import { detectLanguage } from "$lib/utils/langDetect";
    import { indentationMarkers } from "@replit/codemirror-indentation-markers";

    // ── Props ────────────────────────────────────────────────────────────────
    interface Props {
        blockId: string;
        initialCode: string;
        initialLanguage: string;
        onchange: (blockId: string, code: string) => void;
        onlanguagechange: (blockId: string, lang: string) => void;
        onescape: (blockId: string) => void;
        className?: string;
    }

    let {
        blockId,
        initialCode,
        initialLanguage,
        onchange,
        onlanguagechange,
        onescape,
        className = "",
    }: Props = $props();

    // ── Custom theme matching Vadapav palette ────────────────────────────────
    const sushiTheme = EditorView.theme({
        "&": {
            fontSize: "13px",
            fontFamily: "'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace",
            background: "#171717",        // neutral-900
            color: "#d4d4d4",
        },
        "&.cm-focused": {
            outline: "none",
        },
        ".cm-gutters": {
            background: "#171717",
            borderRight: "1px solid #262626",  // neutral-800
            color: "#525252",                  // neutral-600
        },
        ".cm-activeLineGutter": {
            background: "rgba(249, 115, 22, 0.06)",
            color: "#737373",                  // neutral-500
        },
        ".cm-activeLine": {
            background: "rgba(255, 255, 255, 0.02)",
        },
        ".cm-cursor": {
            borderLeftColor: "#f97316",        // orange-500
            borderLeftWidth: "2px",
        },
        ".cm-content": {
            caretColor: "#f97316",
            padding: "8px 0",
        },
        ".cm-scroller": {
            overflow: "auto",
            lineHeight: "1.6",
        },
        ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
            background: "rgba(249, 115, 22, 0.15) !important",
        },
        ".cm-matchingBracket": {
            background: "rgba(249, 115, 22, 0.2)",
            color: "#f97316 !important",
            outline: "1px solid rgba(249, 115, 22, 0.3)",
        },
        ".cm-searchMatch": {
            background: "rgba(249, 115, 22, 0.2)",
        },
        ".cm-tooltip": {
            background: "#1e1e1e",
            border: "1px solid #333",
        },
    }, { dark: true });

    // Syntax highlighting matching the app's warm/neutral palette
    const sushiHighlight = HighlightStyle.define([
        { tag: tags.keyword,        color: "#c084fc" }, // purple-400
        { tag: tags.controlKeyword, color: "#c084fc" },
        { tag: tags.operator,       color: "#a3a3a3" }, // neutral-400
        { tag: tags.punctuation,    color: "#737373" }, // neutral-500
        { tag: tags.bracket,        color: "#a3a3a3" },
        { tag: tags.string,         color: "#fb923c" }, // orange-400
        { tag: tags.regexp,         color: "#fb923c" },
        { tag: tags.number,         color: "#38bdf8" }, // sky-400
        { tag: tags.bool,           color: "#38bdf8" },
        { tag: tags.null,           color: "#38bdf8" },
        { tag: tags.function(tags.variableName), color: "#fbbf24" }, // amber-400
        { tag: tags.function(tags.definition(tags.variableName)), color: "#fbbf24" },
        { tag: tags.definition(tags.variableName), color: "#e5e5e5" },
        { tag: tags.variableName,   color: "#d4d4d4" },
        { tag: tags.propertyName,   color: "#60a5fa" }, // blue-400
        { tag: tags.definition(tags.propertyName), color: "#60a5fa" },
        { tag: tags.typeName,       color: "#34d399" }, // emerald-400
        { tag: tags.className,      color: "#34d399" },
        { tag: tags.labelName,      color: "#fbbf24" },
        { tag: tags.comment,        color: "#525252", fontStyle: "italic" }, // neutral-600
        { tag: tags.lineComment,    color: "#525252", fontStyle: "italic" },
        { tag: tags.blockComment,   color: "#525252", fontStyle: "italic" },
        { tag: tags.docComment,     color: "#6b7280", fontStyle: "italic" }, // gray-500
        { tag: tags.meta,           color: "#737373" },
        { tag: tags.tagName,        color: "#f87171" }, // red-400 (HTML tags)
        { tag: tags.attributeName,  color: "#fb923c" },
        { tag: tags.attributeValue, color: "#fbbf24" },
        { tag: tags.heading,        color: "#f0f0f0", fontWeight: "bold" },
        { tag: tags.emphasis,       fontStyle: "italic" },
        { tag: tags.strong,         fontWeight: "bold" },
        { tag: tags.atom,           color: "#38bdf8" },
        { tag: tags.self,           color: "#c084fc" },
        { tag: tags.special(tags.variableName), color: "#f97316" },
    ]);

    // ── Language configuration ───────────────────────────────────────────────
    const LANGUAGES: Record<string, { label: string; ext: () => ReturnType<typeof python> }> = {
        plaintext: { label: "Plaintext", ext: () => [] as any },
        python:     { label: "Python",     ext: python },
        javascript: { label: "JavaScript", ext: javascript },
        sql:        { label: "SQL",        ext: sql },
        rust:       { label: "Rust",       ext: rust },
        go:         { label: "Go",         ext: go },
        html:       { label: "HTML",       ext: html },
        css:        { label: "CSS",        ext: css },
    };

    const LANG_KEYS = Object.keys(LANGUAGES);

    // ── State ─────────────────────────────────────────────────────────────────
    let containerEl = $state<HTMLDivElement | null>(null);
    let editorView: EditorView | null = null;
    let langSelector = $state(false);
    let wrapperEl = $state<HTMLDivElement | null>(null);
    let currentLang = $state(initialLanguage || "plaintext");
    let collapsed = $state(false);
    let copyFeedback = $state(false);
    let firstLine = $state("");

    // Compartment for dynamic language switching
    const langCompartment = new Compartment();

    // ── Helpers ──────────────────────────────────────────────────────────────

    function getLangExtension(lang: string) {
        const entry = LANGUAGES[lang];
        if (!entry || lang === "plaintext") return [];
        return entry.ext();
    }

    function updateFirstLine(doc?: string) {
        const text = doc ?? editorView?.state.doc.toString() ?? initialCode;
        const nl = text.indexOf("\n");
        firstLine = nl >= 0 ? text.slice(0, Math.min(nl, 60)) : text.slice(0, 60);
        if (firstLine.length === 60) firstLine += "…";
    }

    // ── CodeMirror setup (reactive — reinitializes when container appears) ──

    // Track last known doc content to preserve across collapse/expand
    let lastDoc: string = initialCode;

    // Guard: track which DOM element we've already initialized for,
    // so the $effect doesn't re-create CodeMirror on unrelated reactivity.
    let initializedForEl: HTMLDivElement | null = null;

    $effect(() => {
        const el = containerEl;
        if (!el) return;

        // If we've already created an editor for this exact element, skip.
        if (initializedForEl === el && editorView) return;
        initializedForEl = el;

        updateFirstLine(lastDoc);

        const escapeKeymap = keymap.of([
            {
                key: "Escape",
                run: () => {
                    editorView?.contentDOM.blur();
                    onescape(blockId);
                    return true;
                },
            },
        ]);

        const updateListener = EditorView.updateListener.of((update) => {
            if (update.docChanged) {
                const code = update.state.doc.toString();
                lastDoc = code;
                onchange(blockId, code);
                updateFirstLine(code);
            }
        });

        // Paste handler for language auto-detection
        const pasteHandler = EditorView.domEventHandlers({
            paste: (_event: ClipboardEvent, view: EditorView) => {
                // Wait for CodeMirror to process the paste before running detection
                setTimeout(() => {
                    try {
                        // Guard: editor may have been destroyed between paste and callback
                        if (!editorView || editorView !== view) return;
                        if (currentLang !== "plaintext") return;
                        const doc = view.state.doc.toString();
                        if (!doc.trim()) return;
                        const detected = detectLanguage(doc);
                        if (detected !== "plaintext") {
                            setLanguage(detected);
                        }
                    } catch (err) {
                        console.warn("Language detection failed after paste:", err);
                    }
                }, 50);
                return false;
            },
        });

        // Trap Tab key so the browser doesn't shift focus out of the editor
        const tabTrap = EditorView.domEventHandlers({
            keydown: (event: KeyboardEvent) => {
                if (event.key === "Tab") {
                    // Don't let the browser move focus away —
                    // CodeMirror's indentWithTab will handle the actual indent
                    event.preventDefault();
                    return false; // let CodeMirror keymaps handle it
                }
                return false;
            },
        });

        const state = EditorState.create({
            doc: lastDoc,
            extensions: [
                // Key bindings: escape first so it takes priority
                escapeKeymap,
                keymap.of([indentWithTab]),
                keymap.of(defaultKeymap),
                keymap.of(historyKeymap),
                history(),

                // Indent unit: 2 spaces
                indentUnit.of("    "),

                // Editor features
                lineNumbers(),
                highlightActiveLine(),
                drawSelection(),
                indentOnInput(),
                bracketMatching(),
                closeBrackets(),

                // Language (dynamic via compartment)
                langCompartment.of(getLangExtension(currentLang)),

                // Theme: custom Sushi theme instead of oneDark
                sushiTheme,
                syntaxHighlighting(sushiHighlight),

                // Listeners
                updateListener,
                pasteHandler,
                tabTrap,

                // Indent guides
                indentationMarkers({
                    hideFirstIndent: false,
                    highlightActiveBlock: true,
                    thickness: 1,
                }),
            ],
        });

        editorView = new EditorView({
            state,
            parent: el,
        });

        return () => {
            // Save doc before destroy so we can restore on expand
            if (editorView) {
                lastDoc = editorView.state.doc.toString();
            }
            editorView?.destroy();
            editorView = null;
            initializedForEl = null;
        };
    });

    // ── Language switching ────────────────────────────────────────────────────

    function setLanguage(lang: string) {
        currentLang = lang;
        langSelector = false;
        onlanguagechange(blockId, lang);

        if (editorView) {
            editorView.dispatch({
                effects: langCompartment.reconfigure(getLangExtension(lang)),
            });
        }
    }

    /** Close dropdown when clicking anywhere outside the selector */
    function handleWindowClick(e: MouseEvent) {
        if (!langSelector) return;
        const target = e.target as HTMLElement;
        if (target.closest(".lang-selector-wrap")) return;
        langSelector = false;
    }

    // ── Copy to clipboard ────────────────────────────────────────────────────

    async function handleCopy() {
        const code = lastDoc;
        try {
            await navigator.clipboard.writeText(code.trim());
            copyFeedback = true;
            setTimeout(() => (copyFeedback = false), 1500);
        } catch {
            const ta = document.createElement("textarea");
            ta.value = code.trim();
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
            copyFeedback = true;
            setTimeout(() => (copyFeedback = false), 1500);
        }
    }

    // ── Collapse ──────────────────────────────────────────────────────────────

    function toggleCollapse() {
        collapsed = !collapsed;
    }

    // ── Exported API ─────────────────────────────────────────────────────────

    export function getContent(): string {
        return editorView?.state.doc.toString() ?? lastDoc;
    }

    export function focus() {
        editorView?.focus();
    }
</script>

<svelte:window onclick={handleWindowClick} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
    bind:this={wrapperEl}
    class="code-block-wrapper {className}"
    class:dropdown-open={langSelector}
    data-block-id={blockId}
>
    <!-- Header bar -->
    <div class="code-header">
        <!-- Collapse toggle -->
        <button
            class="collapse-btn"
            onclick={toggleCollapse}
            title={collapsed ? "Expand" : "Collapse"}
        >
            <span class="chevron" class:chevron-open={!collapsed}>›</span>
        </button>

        <!-- Language selector -->
        <div class="lang-selector-wrap">
            <button
                class="lang-label"
                onclick={() => (langSelector = !langSelector)}
                title="Change language"
            >
                {LANGUAGES[currentLang]?.label ?? "Plaintext"}
            </button>
            {#if langSelector}
                <div class="lang-dropdown">
                    {#each LANG_KEYS as key}
                        <button
                            class="lang-option"
                            class:lang-active={key === currentLang}
                            onclick={() => setLanguage(key)}
                        >
                            {LANGUAGES[key].label}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>

        {#if collapsed}
            <!-- First line preview when collapsed -->
            <span class="collapsed-preview">{firstLine || "empty"}</span>
        {/if}

        <div class="header-spacer"></div>

        <!-- Copy button -->
        <button
            class="copy-btn"
            onclick={handleCopy}
            title="Copy code"
        >
            {#if copyFeedback}
                <span class="copy-check">✓</span>
            {:else}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
            {/if}
        </button>
    </div>

    <!-- Editor body -->
    {#if !collapsed}
        <div class="code-editor-container" bind:this={containerEl}></div>
    {/if}
</div>

<style>
    .code-block-wrapper {
        border: 1px solid #262626;         /* neutral-800 */
        border-radius: 8px;
        overflow: visible;                 /* Allow dropdown to overflow */
        background: #171717;              /* neutral-900 */
        position: relative;
        z-index: 1;
    }
    /* Raise above other blocks when dropdown is open */
    .code-block-wrapper.dropdown-open {
        z-index: 100;
    }

    /* ── Header ──────────────────────────────────────────────── */
    .code-header {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        background: #141414;
        border-bottom: 1px solid #262626;  /* neutral-800 */
        min-height: 30px;
        border-radius: 8px 8px 0 0;
    }

    .collapse-btn {
        background: none;
        border: none;
        color: #525252;                    /* neutral-600 */
        cursor: pointer;
        padding: 0 4px;
        font-size: 14px;
        line-height: 1;
        transition: color 0.15s;
        display: flex;
        align-items: center;
    }
    .collapse-btn:hover {
        color: #a3a3a3;                    /* neutral-400 */
    }
    .chevron {
        display: inline-block;
        transition: transform 0.2s ease;
        transform: rotate(0deg);
    }
    .chevron-open {
        transform: rotate(90deg);
    }

    .header-spacer {
        flex: 1;
    }

    .collapsed-preview {
        font-family: "Fira Code", "Cascadia Code", monospace;
        font-size: 11px;
        color: #525252;                    /* neutral-600 */
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 400px;
    }

    /* ── Language selector ────────────────────────────────────── */
    .lang-selector-wrap {
        position: relative;
        z-index: 50;
    }
    .lang-label {
        background: none;
        border: none;
        color: #737373;                    /* neutral-500 */
        font-size: 11px;
        font-family: inherit;
        cursor: pointer;
        padding: 2px 8px;
        border-radius: 4px;
        transition: background 0.15s, color 0.15s;
    }
    .lang-label:hover {
        background: #262626;              /* neutral-800 */
        color: #d4d4d4;
    }
    .lang-dropdown {
        position: absolute;
        top: 100%;
        left: 0;
        margin-top: 4px;
        background: #1c1c1c;
        border: 1px solid #333;
        border-radius: 6px;
        padding: 4px 0;
        z-index: 200;
        min-width: 130px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .lang-option {
        display: block;
        width: 100%;
        text-align: left;
        background: none;
        border: none;
        color: #a3a3a3;                   /* neutral-400 */
        font-size: 12px;
        padding: 5px 14px;
        cursor: pointer;
        transition: background 0.1s, color 0.1s;
    }
    .lang-option:hover {
        background: #262626;
        color: #f5f5f5;
    }
    .lang-option.lang-active {
        color: #f97316;                    /* orange-500 */
        font-weight: 600;
    }



    /* ── Copy button ─────────────────────────────────────────── */
    .copy-btn {
        background: none;
        border: none;
        color: #525252;                    /* neutral-600 */
        cursor: pointer;
        padding: 3px 6px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        transition: background 0.15s, color 0.15s;
    }
    .copy-btn:hover {
        background: #262626;
        color: #d4d4d4;
    }
    .copy-check {
        color: #22c55e;                    /* green-500 */
        font-size: 13px;
        font-weight: 700;
    }

    /* ── Editor container (height cap applied here) ───────────── */
    .code-editor-container {
        max-height: 400px;
        overflow-y: auto;
        border-radius: 0 0 8px 8px;
    }

    /* ── Dark scrollbar styling ──────────────────────────────── */
    .code-editor-container::-webkit-scrollbar {
        width: 8px;
    }
    .code-editor-container::-webkit-scrollbar-track {
        background: #141414;
    }
    .code-editor-container::-webkit-scrollbar-thumb {
        background: #333;
        border-radius: 4px;
    }
    .code-editor-container::-webkit-scrollbar-thumb:hover {
        background: #444;
    }

    /* CodeMirror global overrides */
    :global(.code-editor-container .cm-editor) {
        background: #171717;              /* neutral-900 */
    }
    :global(.code-editor-container .cm-scroller) {
        font-family: "Fira Code", "Cascadia Code", "JetBrains Mono", monospace;
        font-size: 13px;
    }
    :global(.code-editor-container .cm-scroller::-webkit-scrollbar) {
        width: 8px;
        height: 8px;
    }
    :global(.code-editor-container .cm-scroller::-webkit-scrollbar-track) {
        background: transparent;
    }
    :global(.code-editor-container .cm-scroller::-webkit-scrollbar-thumb) {
        background: #333;
        border-radius: 4px;
    }
    :global(.code-editor-container .cm-scroller::-webkit-scrollbar-thumb:hover) {
        background: #444;
    }

    /* ── Indent guide lines ──────────────────────────────────── */
    :global(.code-editor-container .cm-activeLine .cm-indent-markers::before) {
        border-color: rgba(249, 115, 22, 0.25) !important;
    }
    :global(.code-editor-container .cm-indent-markers::before) {
        border-color: rgba(255, 255, 255, 0.06) !important;
    }
</style>
