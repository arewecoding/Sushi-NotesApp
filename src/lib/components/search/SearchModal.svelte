<script lang="ts">
    import {
        Search,
        X,
        Clock,
        FileText,
        Zap,
        Brain,
        Loader2,
    } from "lucide-svelte";
    import { fade, scale } from "svelte/transition";
    import { isSearchOpen } from "$lib/stores/layoutStore";
    import { loadNote } from "$lib/stores/notesStore";
    import {
        searchResults,
        searchTier,
        searchLoading,
        selectedIndex,
        lastQuery,
        recentSearches,
        performSearch,
        switchToDeep,
        resetSearch,
        addRecentSearch,
    } from "$lib/stores/searchStore";

    let searchQuery = $state("");
    let searchInput: HTMLInputElement;

    function close() {
        $isSearchOpen = false;
        searchQuery = "";
        resetSearch();
    }

    function handleInput() {
        performSearch(searchQuery);
    }

    async function selectResult(result: {
        noteId: string;
        noteTitle?: string;
    }) {
        addRecentSearch(searchQuery);
        close();
        await loadNote(result.noteId);
    }

    function handleRecentClick(query: string) {
        searchQuery = query;
        performSearch(query);
        searchInput?.focus();
    }

    function handleKeydown(e: KeyboardEvent) {
        // Only handle keys when the search modal is actually open
        if (!$isSearchOpen) return;

        if (e.key === "Escape") {
            close();
            return;
        }

        const results = $searchResults;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            $selectedIndex = Math.min($selectedIndex + 1, results.length - 1);
            return;
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            $selectedIndex = Math.max($selectedIndex - 1, -1);
            return;
        }

        if (
            e.key === "Enter" &&
            $selectedIndex >= 0 &&
            results[$selectedIndex]
        ) {
            e.preventDefault();
            selectResult(results[$selectedIndex]);
            return;
        }

        if (e.key === "Tab" && searchQuery.trim()) {
            e.preventDefault();
            if ($searchTier === "fast") {
                switchToDeep(searchQuery);
            }
        }
    }

    // Scroll selected result into view
    $effect(() => {
        const idx = $selectedIndex;
        if (idx >= 0) {
            const el = document.getElementById(`search-result-${idx}`);
            el?.scrollIntoView({ block: "nearest" });
        }
    });
</script>

<svelte:window onkeydown={handleKeydown} />

{#if $isSearchOpen}
    <div
        class="search-overlay"
        transition:fade={{ duration: 150 }}
        onclick={close}
        role="dialog"
        aria-label="Search"
    >
        <div
            class="search-modal"
            transition:scale={{ start: 0.95, duration: 150 }}
            onclick={(e) => e.stopPropagation()}
        >
            <!-- Search Header -->
            <div class="search-header">
                <Search class="search-icon" size={22} />
                <input
                    bind:this={searchInput}
                    bind:value={searchQuery}
                    oninput={handleInput}
                    type="text"
                    placeholder="Search notes..."
                    class="search-input"
                    autofocus
                />
                {#if $searchLoading}
                    <div class="search-spinner">
                        <Loader2 size={18} class="animate-spin" />
                    </div>
                {/if}
                <button
                    class="search-clear-btn"
                    onclick={() => {
                        if (searchQuery) {
                            searchQuery = "";
                            resetSearch();
                            searchInput.focus();
                        } else {
                            close();
                        }
                    }}
                >
                    <X size={18} />
                </button>
            </div>

            <!-- Tier Indicator -->
            {#if searchQuery.trim() && $searchTier === "deep"}
                <div class="tier-indicator">
                    <Brain size={14} />
                    <span>Deep Search</span>
                </div>
            {/if}

            <!-- Content Area -->
            <div class="search-content">
                {#if searchQuery === ""}
                    <!-- Recent Searches -->
                    {#if $recentSearches.length > 0}
                        <div class="section-label">Recent</div>
                        <div class="results-list">
                            {#each $recentSearches as query}
                                <button
                                    class="result-item"
                                    onclick={() => handleRecentClick(query)}
                                >
                                    <Clock
                                        size={16}
                                        class="result-icon result-icon-recent"
                                    />
                                    <span class="result-title">{query}</span>
                                </button>
                            {/each}
                        </div>
                    {:else}
                        <div class="empty-state">
                            <Search size={32} class="empty-icon" />
                            <p>Search your notes with <kbd>Ctrl+K</kbd></p>
                        </div>
                    {/if}
                {:else if $searchResults.length === 0 && !$searchLoading}
                    <!-- Zero Results -->
                    <div class="empty-state">
                        <p class="empty-text">No results for "{searchQuery}"</p>
                        {#if $searchTier === "fast"}
                            <button
                                class="deep-search-btn"
                                onclick={() => switchToDeep(searchQuery)}
                            >
                                <Brain size={16} />
                                <span>Try deep search</span>
                            </button>
                        {:else}
                            <p class="empty-hint">Try different keywords</p>
                        {/if}
                    </div>
                {:else}
                    <!-- Results -->
                    {#if $searchTier === "fast"}
                        <!-- Separate into notes and blocks -->
                        {@const noteResults = $searchResults.filter(
                            (r) => r.resultType === "note",
                        )}
                        {@const blockResults = $searchResults.filter(
                            (r) => r.resultType === "block",
                        )}

                        {#if noteResults.length > 0}
                            <div class="section-label">Notes</div>
                            <div class="results-list">
                                {#each noteResults as result, i}
                                    {@const globalIdx = i}
                                    <button
                                        id="search-result-{globalIdx}"
                                        class="result-item"
                                        class:selected={$selectedIndex ===
                                            globalIdx}
                                        onclick={() => selectResult(result)}
                                        onmouseenter={() =>
                                            ($selectedIndex = globalIdx)}
                                    >
                                        <FileText
                                            size={16}
                                            class="result-icon result-icon-note"
                                        />
                                        <div class="result-content">
                                            <div class="result-title">
                                                {result.noteTitle}
                                            </div>
                                        </div>
                                    </button>
                                {/each}
                            </div>
                        {/if}

                        {#if blockResults.length > 0}
                            <div class="section-label">Content</div>
                            <div class="results-list">
                                {#each blockResults as result, i}
                                    {@const globalIdx = noteResults.length + i}
                                    <button
                                        id="search-result-{globalIdx}"
                                        class="result-item"
                                        class:selected={$selectedIndex ===
                                            globalIdx}
                                        onclick={() => selectResult(result)}
                                        onmouseenter={() =>
                                            ($selectedIndex = globalIdx)}
                                    >
                                        <Zap
                                            size={16}
                                            class="result-icon result-icon-block"
                                        />
                                        <div class="result-content">
                                            <div class="result-title">
                                                {result.noteTitle}
                                            </div>
                                            {#if result.blockSnippet}
                                                <div class="result-snippet">
                                                    {result.blockSnippet}
                                                </div>
                                            {/if}
                                        </div>
                                    </button>
                                {/each}
                            </div>
                        {/if}
                    {:else}
                        <!-- Deep search results (single list) -->
                        <div class="section-label">
                            <Brain size={12} />
                            Semantic Results
                        </div>
                        <div class="results-list">
                            {#each $searchResults as result, i}
                                <button
                                    id="search-result-{i}"
                                    class="result-item"
                                    class:selected={$selectedIndex === i}
                                    onclick={() => selectResult(result)}
                                    onmouseenter={() => ($selectedIndex = i)}
                                >
                                    <Brain
                                        size={16}
                                        class="result-icon result-icon-deep"
                                    />
                                    <div class="result-content">
                                        <div class="result-title">
                                            {result.noteTitle}
                                        </div>
                                        {#if result.blockSnippet}
                                            <div class="result-snippet">
                                                {result.blockSnippet}
                                            </div>
                                        {/if}
                                    </div>
                                    {#if result.score}
                                        <span class="result-score">
                                            {Math.round(
                                                (result.score ?? 0) * 100,
                                            )}%
                                        </span>
                                    {/if}
                                </button>
                            {/each}
                        </div>
                    {/if}
                {/if}
            </div>

            <!-- Footer -->
            <div class="search-footer">
                <div class="footer-hint">
                    <kbd>↑↓</kbd>
                    <span>navigate</span>
                </div>
                <div class="footer-hint">
                    <kbd>↵</kbd>
                    <span>open</span>
                </div>
                <div class="footer-hint">
                    <kbd>tab</kbd>
                    <span>deep search</span>
                </div>
                <div class="footer-hint">
                    <kbd>esc</kbd>
                    <span>close</span>
                </div>
            </div>
        </div>
    </div>
{/if}

<style>
    .search-overlay {
        position: fixed;
        inset: 0;
        z-index: 50;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding-top: 15vh;
        background: rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(8px);
    }

    .search-modal {
        width: 100%;
        max-width: 640px;
        background: rgba(24, 24, 27, 0.95);
        border: 1px solid rgba(63, 63, 70, 0.6);
        border-radius: 16px;
        box-shadow:
            0 25px 60px rgba(0, 0, 0, 0.5),
            0 0 0 1px rgba(255, 255, 255, 0.05);
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    /* Header */
    .search-header {
        display: flex;
        align-items: center;
        padding: 16px 20px;
        gap: 14px;
        border-bottom: 1px solid rgba(63, 63, 70, 0.4);
    }

    :global(.search-icon) {
        color: #71717a;
        flex-shrink: 0;
    }

    .search-input {
        flex: 1;
        background: transparent;
        border: none;
        outline: none;
        font-size: 1.125rem;
        color: #e4e4e7;
        font-family: inherit;
    }

    .search-input::placeholder {
        color: #52525b;
    }

    .search-spinner {
        display: flex;
        align-items: center;
        color: #a78bfa;
    }

    :global(.animate-spin) {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from {
            transform: rotate(0deg);
        }
        to {
            transform: rotate(360deg);
        }
    }

    .search-clear-btn {
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

    .search-clear-btn:hover {
        color: #d4d4d8;
    }

    /* Tier Indicator */
    .tier-indicator {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 20px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #c084fc;
        background: rgba(168, 85, 247, 0.08);
        border-bottom: 1px solid rgba(168, 85, 247, 0.15);
    }

    /* Content */
    .search-content {
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
        margin-bottom: 8px;
    }

    .result-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        width: 100%;
        background: none;
        border: none;
        border-radius: 10px;
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

    :global(.result-icon-recent) {
        color: #71717a;
    }

    :global(.result-icon-deep) {
        color: #c084fc;
    }

    .result-content {
        flex: 1;
        min-width: 0;
        overflow: hidden;
    }

    .result-title {
        font-size: 0.9rem;
        font-weight: 500;
        color: #e4e4e7;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .result-snippet {
        font-size: 0.78rem;
        color: #a1a1aa;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-top: 2px;
    }

    .result-score {
        font-size: 0.7rem;
        font-weight: 600;
        color: #a78bfa;
        padding: 2px 8px;
        background: rgba(168, 85, 247, 0.12);
        border-radius: 99px;
        flex-shrink: 0;
    }

    /* Empty States */
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 40px 20px;
        gap: 12px;
    }

    :global(.empty-icon) {
        color: #3f3f46;
    }

    .empty-state p {
        color: #71717a;
        font-size: 0.85rem;
    }

    .empty-state kbd {
        padding: 2px 8px;
        background: rgba(63, 63, 70, 0.5);
        border: 1px solid rgba(82, 82, 91, 0.5);
        border-radius: 5px;
        font-size: 0.75rem;
        font-family: inherit;
        color: #a1a1aa;
    }

    .empty-text {
        color: #a1a1aa !important;
        font-weight: 500;
    }

    .empty-hint {
        font-size: 0.78rem !important;
    }

    .deep-search-btn {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 18px;
        background: rgba(168, 85, 247, 0.1);
        border: 1px solid rgba(168, 85, 247, 0.25);
        border-radius: 10px;
        color: #c084fc;
        font-size: 0.82rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s;
        font-family: inherit;
    }

    .deep-search-btn:hover {
        background: rgba(168, 85, 247, 0.18);
        border-color: rgba(168, 85, 247, 0.4);
    }

    /* Footer */
    .search-footer {
        display: flex;
        justify-content: flex-end;
        gap: 16px;
        padding: 10px 16px;
        border-top: 1px solid rgba(63, 63, 70, 0.4);
        background: rgba(9, 9, 11, 0.4);
    }

    .footer-hint {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 0.68rem;
        color: #52525b;
    }

    .footer-hint kbd {
        padding: 1px 6px;
        background: rgba(63, 63, 70, 0.5);
        border: 1px solid rgba(82, 82, 91, 0.4);
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.65rem;
        color: #71717a;
    }
</style>
