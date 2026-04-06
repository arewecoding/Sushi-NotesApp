<script lang="ts">
    /**
     * LinkModal.svelte — Centered omni-search modal for creating links
     * =================================================================
     * Two modes:
     *   1. Global omni-search: queries notes + blocks simultaneously
     *   2. Drill-down: scoped to a single note's blocks
     *
     * Also detects URLs and offers "Link to [url]" insertion.
     */
    import { fade, scale } from "svelte/transition";
    import {
        Search,
        X,
        FileText,
        Zap,
        ChevronRight,
        Globe,
        Loader2,
    } from "lucide-svelte";
    import {
        isLinkModalOpen,
        linkModalContext,
        closeLinkModal,
    } from "$lib/stores/linkModalStore";
    import { searchFast, searchDeep } from "$lib/client/apiClient";
    import { openNote } from "$lib/client/apiClient";
    import { serializeLink } from "$lib/utils/linkParser";
    import type { SearchResultItem, NoteBlock } from "$lib/client/_apiTypes";

    // ── State ─────────────────────────────────────────────────────────────
    let query = $state("");
    let searchInput = $state<HTMLInputElement | null>(null);
    let results = $state<SearchResultItem[]>([]);
    let loading = $state(false);
    let selectedIndex = $state(-1);
    let searchTier = $state<"fast" | "deep">("fast");

    // Drill-down state
    let mode = $state<"global" | "scoped">("global");
    let scopedNoteId = $state<string | null>(null);
    let scopedNoteTitle = $state("");
    let scopedBlocks = $state<NoteBlock[]>([]);
    let filteredBlocks = $state<NoteBlock[]>([]);

    // URL detection
    const URL_PATTERN = /^(https?:\/\/|[a-z0-9][a-z0-9-]*\.[a-z]{2,})/i;
    let detectedUrl = $state<string | null>(null);

    // Debounce
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    const DEBOUNCE_MS = 150;

    // ── Reactive: focus input when modal opens ───────────────────────────
    $effect(() => {
        if ($isLinkModalOpen) {
            resetState();
            // Pre-populate from context
            const ctx = $linkModalContext;
            if (ctx && ctx.displayText) {
                const q = ctx.displayText.length > 60
                    ? ctx.displayText.slice(0, 60)
                    : ctx.displayText;
                query = q;
                // Trigger search with pre-populated text
                debouncedSearch(q);
            }
            // Focus input after DOM update
            requestAnimationFrame(() => {
                searchInput?.focus();
                if (query) searchInput?.select();
            });
        }
    });

    function resetState() {
        query = "";
        results = [];
        loading = false;
        selectedIndex = -1;
        mode = "global";
        scopedNoteId = null;
        scopedNoteTitle = "";
        scopedBlocks = [];
        filteredBlocks = [];
        detectedUrl = null;
        searchTier = "fast";
    }

    // ── Search ────────────────────────────────────────────────────────────

    function handleInput() {
        const q = query;

        if (mode === "scoped") {
            // Filter blocks within the scoped note
            filterBlocks(q);
            return;
        }

        // URL detection (only after 4+ chars)
        if (q.length >= 4 && URL_PATTERN.test(q.trim())) {
            detectedUrl = q.trim();
            results = [];
            loading = false;
            selectedIndex = 0;
            return;
        } else {
            detectedUrl = null;
        }

        debouncedSearch(q);
    }

    function debouncedSearch(q: string) {
        selectedIndex = -1;

        if (!q.trim()) {
            results = [];
            loading = false;
            return;
        }

        loading = true;
        if (debounceTimer) clearTimeout(debounceTimer);

        debounceTimer = setTimeout(async () => {
            try {
                const response = await searchFast(q, 15);
                results = response.results;
                searchTier = "fast";
            } catch (err) {
                console.error("Link search failed:", err);
                results = [];
            } finally {
                loading = false;
            }
        }, DEBOUNCE_MS);
    }

    async function switchToDeep(q: string) {
        if (!q.trim()) return;
        loading = true;
        searchTier = "deep";
        selectedIndex = -1;
        try {
            const response = await searchDeep(q, 15);
            results = response.results;
        } catch (err) {
            console.error("Link deep search failed:", err);
            results = [];
        } finally {
            loading = false;
        }
    }

    // ── Drill-down ────────────────────────────────────────────────────────

    async function enterDrillDown(noteId: string, noteTitle: string) {
        mode = "scoped";
        scopedNoteId = noteId;
        scopedNoteTitle = noteTitle;
        query = "";
        results = [];
        loading = true;
        selectedIndex = -1;

        try {
            // Use raw openNote from apiClient — pure fetch, no side effects
            const noteContent = await openNote(noteId);
            if (noteContent) {
                scopedBlocks = noteContent.blocks;
                filteredBlocks = noteContent.blocks;
            }
        } catch (err) {
            console.error("Failed to load note blocks:", err);
            scopedBlocks = [];
            filteredBlocks = [];
        } finally {
            loading = false;
        }

        requestAnimationFrame(() => searchInput?.focus());
    }

    function exitDrillDown() {
        mode = "global";
        scopedNoteId = null;
        scopedNoteTitle = "";
        scopedBlocks = [];
        filteredBlocks = [];
        query = "";
        results = [];
        selectedIndex = -1;
        requestAnimationFrame(() => searchInput?.focus());
    }

    function filterBlocks(q: string) {
        const lower = q.toLowerCase().trim();
        if (!lower) {
            filteredBlocks = scopedBlocks;
        } else {
            filteredBlocks = scopedBlocks.filter((b) => {
                const text = (b.data?.content || b.data?.code || "").toString().toLowerCase();
                return text.includes(lower);
            });
        }
        selectedIndex = filteredBlocks.length > 0 ? 0 : -1;
    }

    // ── Result helpers ────────────────────────────────────────────────────

    function getBlockPreview(block: NoteBlock): string {
        const raw = (block.data?.content || block.data?.code || "").toString();
        const firstLine = raw.split("\n")[0] || "";
        return firstLine.length > 80 ? firstLine.slice(0, 80) + "…" : firstLine || `[${block.type} block]`;
    }

    // ── Count helpers for global mode ─────────────────────────────────────
    // Computed derived values for the template
    let noteResults = $derived(results.filter((r) => r.resultType === "note"));
    let blockResults = $derived(results.filter((r) => r.resultType === "block"));
    let totalItems = $derived(
        detectedUrl ? 1 : mode === "scoped" ? filteredBlocks.length : noteResults.length + blockResults.length
    );

    // ── Confirm ───────────────────────────────────────────────────────────

    function confirmSelection(item: {
        display: string;
        linkType: "note" | "block" | "web";
        target: string;
    }) {
        const ctx = $linkModalContext;
        if (!ctx) return;

        const displayText = ctx.displayText || item.display;
        const syntax = serializeLink(displayText, item.linkType, item.target);
        ctx.insertionCallback(syntax);
        closeLinkModal();
    }

    function confirmUrl() {
        if (!detectedUrl) return;
        // Normalise bare domains
        let url = detectedUrl;
        if (!/^https?:\/\//i.test(url)) {
            url = "https://" + url;
        }
        confirmSelection({
            display: url,
            linkType: "web",
            target: url,
        });
    }

    function confirmNoteResult(result: SearchResultItem) {
        confirmSelection({
            display: result.noteTitle,
            linkType: "note",
            target: result.noteId,
        });
    }

    function confirmBlockResult(result: SearchResultItem) {
        confirmSelection({
            display: result.blockSnippet || result.noteTitle,
            linkType: "block",
            target: `${result.noteId}/${result.blockId}`,
        });
    }

    function confirmScopedBlock(block: NoteBlock) {
        confirmSelection({
            display: getBlockPreview(block),
            linkType: "block",
            target: `${scopedNoteId}/${block.blockId}`,
        });
    }

    // ── Keyboard navigation ───────────────────────────────────────────────

    function handleKeydown(e: KeyboardEvent) {
        if (!$isLinkModalOpen) return;

        if (e.key === "Escape") {
            e.preventDefault();
            if (mode === "scoped") {
                exitDrillDown();
            } else {
                closeLinkModal();
            }
            return;
        }

        if (e.key === "ArrowDown") {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, totalItems - 1);
            scrollSelectedIntoView();
            return;
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            scrollSelectedIntoView();
            return;
        }

        if (e.key === "Backspace" && mode === "scoped" && query === "") {
            e.preventDefault();
            exitDrillDown();
            return;
        }

        if (e.key === "Enter" && selectedIndex >= 0) {
            e.preventDefault();

            if (detectedUrl) {
                confirmUrl();
                return;
            }

            if (mode === "scoped") {
                if (filteredBlocks[selectedIndex]) {
                    confirmScopedBlock(filteredBlocks[selectedIndex]);
                }
                return;
            }

            // Global mode: determine which item is selected
            if (selectedIndex < noteResults.length) {
                confirmNoteResult(noteResults[selectedIndex]);
            } else {
                const blockIdx = selectedIndex - noteResults.length;
                if (blockResults[blockIdx]) {
                    confirmBlockResult(blockResults[blockIdx]);
                }
            }
            return;
        }

        // `>` or Tab on a note result → drill-down
        if ((e.key === ">" || e.key === "Tab") && mode === "global" && selectedIndex >= 0 && selectedIndex < noteResults.length) {
            e.preventDefault();
            const noteResult = noteResults[selectedIndex];
            enterDrillDown(noteResult.noteId, noteResult.noteTitle);
            return;
        }

        // Tab with no note selected → deep search
        if (e.key === "Tab" && mode === "global" && query.trim() && searchTier === "fast") {
            e.preventDefault();
            switchToDeep(query);
            return;
        }
    }

    function scrollSelectedIntoView() {
        requestAnimationFrame(() => {
            const el = document.getElementById(`link-result-${selectedIndex}`);
            el?.scrollIntoView({ block: "nearest" });
        });
    }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if $isLinkModalOpen}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
        class="link-overlay"
        transition:fade={{ duration: 120 }}
        onclick={closeLinkModal}
    >
        <div
            class="link-modal"
            transition:scale={{ start: 0.96, duration: 120 }}
            onclick={(e) => e.stopPropagation()}
        >
            <!-- Header -->
            <div class="link-header">
                {#if mode === "scoped"}
                    <button class="breadcrumb" onclick={exitDrillDown}>
                        <FileText size={14} />
                        <span>{scopedNoteTitle}</span>
                        <ChevronRight size={14} />
                    </button>
                {:else}
                    <Search class="link-search-icon" size={20} />
                {/if}
                <input
                    bind:this={searchInput}
                    bind:value={query}
                    oninput={handleInput}
                    type="text"
                    placeholder={mode === "scoped" ? "Filter blocks…" : "Search notes and blocks…"}
                    class="link-input"
                />
                {#if loading}
                    <div class="link-spinner">
                        <Loader2 size={16} class="animate-spin" />
                    </div>
                {/if}
                <button class="link-close-btn" onclick={closeLinkModal}>
                    <X size={16} />
                </button>
            </div>

            <!-- Content -->
            <div class="link-content">
                {#if detectedUrl}
                    <!-- URL mode -->
                    <div class="results-list">
                        <button
                            id="link-result-0"
                            class="result-item"
                            class:selected={selectedIndex === 0}
                            onclick={confirmUrl}
                            onmouseenter={() => (selectedIndex = 0)}
                        >
                            <Globe size={16} class="result-icon result-icon-web" />
                            <div class="result-content">
                                <div class="result-title">Link to {detectedUrl}</div>
                                <div class="result-subtitle">External link</div>
                            </div>
                        </button>
                    </div>
                {:else if mode === "scoped"}
                    <!-- Drill-down block list -->
                    {#if filteredBlocks.length > 0}
                        <div class="section-label">Blocks in {scopedNoteTitle}</div>
                        <div class="results-list">
                            {#each filteredBlocks as block, i}
                                <button
                                    id="link-result-{i}"
                                    class="result-item"
                                    class:selected={selectedIndex === i}
                                    onclick={() => confirmScopedBlock(block)}
                                    onmouseenter={() => (selectedIndex = i)}
                                >
                                    <Zap size={16} class="result-icon result-icon-block" />
                                    <div class="result-content">
                                        <div class="result-title">{getBlockPreview(block)}</div>
                                        <div class="result-subtitle">{block.type} block</div>
                                    </div>
                                </button>
                            {/each}
                        </div>
                    {:else if !loading}
                        <div class="empty-state">
                            <p>No blocks found</p>
                        </div>
                    {/if}
                {:else if query.trim() && results.length === 0 && !loading}
                    <!-- No results -->
                    <div class="empty-state">
                        <p>No notes or blocks found.</p>
                        {#if searchTier === "fast"}
                            <button class="deep-search-btn" onclick={() => switchToDeep(query)}>
                                Try deep search
                            </button>
                        {/if}
                    </div>
                {:else if results.length > 0}
                    <!-- Global omni-search results -->
                    {#if noteResults.length > 0}
                        <div class="section-label">Notes</div>
                        <div class="results-list">
                            {#each noteResults as result, i}
                                <button
                                    id="link-result-{i}"
                                    class="result-item"
                                    class:selected={selectedIndex === i}
                                    onclick={() => confirmNoteResult(result)}
                                    onmouseenter={() => (selectedIndex = i)}
                                >
                                    <FileText size={16} class="result-icon result-icon-note" />
                                    <div class="result-content">
                                        <div class="result-title">{result.noteTitle}</div>
                                    </div>
                                    <span class="drill-hint" title="Press > to browse blocks">
                                        <ChevronRight size={14} />
                                    </span>
                                </button>
                            {/each}
                        </div>
                    {/if}
                    {#if blockResults.length > 0}
                        <div class="section-label">Blocks</div>
                        <div class="results-list">
                            {#each blockResults as result, i}
                                {@const globalIdx = noteResults.length + i}
                                <button
                                    id="link-result-{globalIdx}"
                                    class="result-item"
                                    class:selected={selectedIndex === globalIdx}
                                    onclick={() => confirmBlockResult(result)}
                                    onmouseenter={() => (selectedIndex = globalIdx)}
                                >
                                    <Zap size={16} class="result-icon result-icon-block" />
                                    <div class="result-content">
                                        <div class="result-title">{result.noteTitle}</div>
                                        {#if result.blockSnippet}
                                            <div class="result-subtitle">{result.blockSnippet}</div>
                                        {/if}
                                    </div>
                                </button>
                            {/each}
                        </div>
                    {/if}
                {:else if !query.trim()}
                    <div class="empty-state">
                        <Search size={28} class="empty-icon" />
                        <p>Search for a note or block to link</p>
                        <p class="empty-hint">Type <kbd>[[</kbd> in the editor to open this modal</p>
                    </div>
                {/if}
            </div>

            <!-- Footer -->
            <div class="link-footer">
                <div class="footer-hint">
                    <kbd>↑↓</kbd>
                    <span>navigate</span>
                </div>
                <div class="footer-hint">
                    <kbd>↵</kbd>
                    <span>select</span>
                </div>
                {#if mode === "global"}
                    <div class="footer-hint">
                        <kbd>&gt;</kbd>
                        <span>drill-down</span>
                    </div>
                {:else}
                    <div class="footer-hint">
                        <kbd>⌫</kbd>
                        <span>back</span>
                    </div>
                {/if}
                <div class="footer-hint">
                    <kbd>esc</kbd>
                    <span>close</span>
                </div>
                {#if mode === "global" && searchTier === "fast"}
                    <div class="footer-hint">
                        <kbd>tab</kbd>
                        <span>deep search</span>
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}

<style>
    .link-overlay {
        position: fixed;
        inset: 0;
        z-index: 60;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding-top: 15vh;
        background: rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(8px);
    }

    .link-modal {
        width: 100%;
        max-width: 600px;
        background: rgba(24, 24, 27, 0.97);
        border: 1px solid rgba(63, 63, 70, 0.6);
        border-radius: 14px;
        box-shadow:
            0 25px 60px rgba(0, 0, 0, 0.5),
            0 0 0 1px rgba(255, 255, 255, 0.05);
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    /* ── Header ──────────────────────────────────────────────── */
    .link-header {
        display: flex;
        align-items: center;
        padding: 14px 18px;
        gap: 12px;
        border-bottom: 1px solid rgba(63, 63, 70, 0.4);
    }

    :global(.link-search-icon) {
        color: #71717a;
        flex-shrink: 0;
    }

    .breadcrumb {
        display: flex;
        align-items: center;
        gap: 4px;
        background: rgba(249, 115, 22, 0.1);
        border: 1px solid rgba(249, 115, 22, 0.2);
        border-radius: 6px;
        padding: 3px 8px;
        color: #f97316;
        font-size: 0.78rem;
        font-weight: 500;
        cursor: pointer;
        flex-shrink: 0;
        transition: background 0.15s;
        font-family: inherit;
    }
    .breadcrumb:hover {
        background: rgba(249, 115, 22, 0.18);
    }

    .link-input {
        flex: 1;
        background: transparent;
        border: none;
        outline: none;
        font-size: 1.05rem;
        color: #e4e4e7;
        font-family: inherit;
    }
    .link-input::placeholder {
        color: #52525b;
    }

    .link-spinner {
        display: flex;
        align-items: center;
        color: #f97316;
    }

    .link-close-btn {
        display: flex;
        align-items: center;
        padding: 4px;
        color: #71717a;
        background: none;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        transition: color 0.15s;
    }
    .link-close-btn:hover {
        color: #d4d4d8;
    }

    /* ── Content ──────────────────────────────────────────────── */
    .link-content {
        max-height: 55vh;
        overflow-y: auto;
        padding: 8px;
    }

    .section-label {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 12px 6px;
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #71717a;
    }

    .results-list {
        display: flex;
        flex-direction: column;
        gap: 2px;
        margin-bottom: 6px;
    }

    .result-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 9px 12px;
        width: 100%;
        background: none;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        text-align: left;
        transition: background 0.12s;
        font-family: inherit;
    }
    .result-item:hover,
    .result-item.selected {
        background: rgba(63, 63, 70, 0.4);
    }

    :global(.result-icon) {
        flex-shrink: 0;
        color: #71717a;
    }
    :global(.result-icon-note) {
        color: #60a5fa;
    }
    :global(.result-icon-block) {
        color: #fbbf24;
    }
    :global(.result-icon-web) {
        color: #38bdf8;
    }

    .result-content {
        flex: 1;
        min-width: 0;
        overflow: hidden;
    }

    .result-title {
        font-size: 0.88rem;
        font-weight: 500;
        color: #e4e4e7;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .result-subtitle {
        font-size: 0.75rem;
        color: #71717a;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-top: 1px;
    }

    .drill-hint {
        flex-shrink: 0;
        color: #3f3f46;
        display: flex;
        align-items: center;
        transition: color 0.15s;
    }
    .result-item:hover .drill-hint,
    .result-item.selected .drill-hint {
        color: #71717a;
    }

    /* ── Empty state ──────────────────────────────────────────── */
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 36px 20px;
        gap: 10px;
    }

    :global(.empty-icon) {
        color: #3f3f46;
    }

    .empty-state p {
        color: #71717a;
        font-size: 0.85rem;
        margin: 0;
    }

    .empty-hint {
        font-size: 0.78rem !important;
        color: #52525b !important;
    }

    .empty-hint kbd {
        padding: 1px 5px;
        background: rgba(63, 63, 70, 0.5);
        border: 1px solid rgba(82, 82, 91, 0.4);
        border-radius: 4px;
        font-size: 0.72rem;
        font-family: inherit;
        color: #a1a1aa;
    }

    .deep-search-btn {
        padding: 6px 14px;
        background: rgba(168, 85, 247, 0.1);
        border: 1px solid rgba(168, 85, 247, 0.25);
        border-radius: 8px;
        color: #c084fc;
        font-size: 0.8rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s;
        font-family: inherit;
    }
    .deep-search-btn:hover {
        background: rgba(168, 85, 247, 0.18);
        border-color: rgba(168, 85, 247, 0.4);
    }

    /* ── Footer ───────────────────────────────────────────────── */
    .link-footer {
        display: flex;
        justify-content: flex-end;
        gap: 14px;
        padding: 9px 16px;
        border-top: 1px solid rgba(63, 63, 70, 0.4);
        background: rgba(9, 9, 11, 0.4);
    }

    .footer-hint {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 0.66rem;
        color: #52525b;
    }

    .footer-hint kbd {
        padding: 1px 5px;
        background: rgba(63, 63, 70, 0.5);
        border: 1px solid rgba(82, 82, 91, 0.4);
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.62rem;
        color: #71717a;
    }
</style>
