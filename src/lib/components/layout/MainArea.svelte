<script lang="ts">
    import {
        Bold,
        Italic,
        Link,
        List,
        PanelRightOpen,
        PanelRightClose,
        PanelLeftOpen,
        PanelLeftClose,
        Loader2,
    } from "lucide-svelte";
    import { isRightPanelOpen, isLeftPanelOpen } from "$lib/stores/layout";
    import {
        activeNoteContent,
        isLoadingNote,
        activeNoteId,
        isSavingNote,
        saveNoteContentDebounced,
        noteContentVersion,
    } from "$lib/stores/notesStore";
    import type { NoteBlock } from "../../../client/_apiTypes";
    import BlockToolbar from "$lib/components/editor/BlockToolbar.svelte";
    import BlockInserter from "$lib/components/editor/BlockInserter.svelte";
    import GhostBlock from "$lib/components/editor/GhostBlock.svelte";
    import ConfirmDialog from "$lib/components/ConfirmDialog.svelte";

    // Track which note and version we've initialized for
    let initializedNoteId: string | null = null;
    let lastInitializedVersion: number = 0;

    // Non-reactive storage for block content during editing
    // This is PLAIN JS - not $state() - so mutations don't trigger re-renders
    let blockContents: Record<string, string> = {};
    let currentTitle: string = "";
    let currentBlocks: NoteBlock[] = [];

    // Reactive flag to show blocks (but content is managed non-reactively)
    let showBlocks = $state(false);

    // Block interaction state
    let hoveredBlockId = $state<string | null>(null);
    let confirmDeleteOpen = $state(false);
    let pendingDeleteBlockId = $state<string | null>(null);

    // Watch for note changes and initialize ONCE per note
    // Also handles external updates via noteContentVersion
    $effect(() => {
        const content = $activeNoteContent;
        const noteId = $activeNoteId;
        const version = $noteContentVersion;

        // IMPORTANT: Verify content.noteId matches activeNoteId to prevent
        // displaying stale content from a different note during async loading
        if (content && noteId && content.noteId === noteId) {
            // Detect: new note OR version change (external update)
            const isNewNote = noteId !== initializedNoteId;
            const isExternalUpdate =
                noteId === initializedNoteId &&
                version !== lastInitializedVersion;

            if (isNewNote || isExternalUpdate) {
                if (isExternalUpdate) {
                    console.log(
                        "Detected external update, reinitializing view...",
                    );
                }

                // Initialize our non-reactive state
                initializedNoteId = noteId;
                lastInitializedVersion = version;
                currentTitle = content.title;
                currentBlocks = content.blocks;

                // Build content map for blocks
                blockContents = {};
                for (const block of content.blocks) {
                    blockContents[block.blockId] =
                        block.data?.content || block.data?.code || "";
                }

                // Trigger re-render to show the new blocks
                showBlocks = false;
                // Use microtask to ensure DOM updates
                queueMicrotask(() => {
                    showBlocks = true;
                });
            }
        }
    });

    // Svelte action to initialize contenteditable ONCE
    function initContent(node: HTMLElement, blockId: string) {
        // Set initial content - this only runs once when element is created
        node.textContent = blockContents[blockId] || "";

        return {
            // No update needed - we don't want reactivity
            destroy() {},
        };
    }

    function handleTitleInput(e: Event) {
        const target = e.target as HTMLTextAreaElement;
        currentTitle = target.value;
        // Auto-resize
        target.style.height = "auto";
        target.style.height = target.scrollHeight + "px";
        // Save
        triggerSave();
    }

    function handleBlockInput(blockId: string, e: Event) {
        const target = e.target as HTMLElement;
        // Update our plain JS storage (no reactivity, no re-render)
        blockContents[blockId] = target.textContent || "";
        // Save
        triggerSave();
    }

    function triggerSave() {
        // Build blocks array from our non-reactive storage
        const blocksToSave = currentBlocks.map((block) => ({
            ...block,
            data: {
                ...block.data,
                content: blockContents[block.blockId] || block.data?.content,
                code:
                    block.type === "code"
                        ? blockContents[block.blockId]
                        : block.data?.code,
            },
        }));
        saveNoteContentDebounced(currentTitle, blocksToSave);
    }

    // ========== Block Operations ==========

    function generateBlockId(): string {
        return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    }

    function createBlock(type: string): NoteBlock {
        return {
            blockId: generateBlockId(),
            type,
            data:
                type === "code"
                    ? { code: "" }
                    : type === "todo"
                      ? { content: "", checked: false }
                      : { content: "" },
            version: "1",
            tags: [],
            backlinks: [],
        };
    }

    function insertBlockAt(index: number, type: string = "text") {
        const newBlock = createBlock(type);
        currentBlocks = [
            ...currentBlocks.slice(0, index),
            newBlock,
            ...currentBlocks.slice(index),
        ];
        blockContents[newBlock.blockId] = "";

        // Re-render and save
        showBlocks = false;
        queueMicrotask(() => {
            showBlocks = true;
            // Focus the new block after render
            queueMicrotask(() => {
                const el = document.querySelector(
                    `[data-block-id="${newBlock.blockId}"]`,
                );
                if (el instanceof HTMLElement) {
                    el.focus();
                }
            });
        });
        triggerSave();
    }

    function appendBlock() {
        insertBlockAt(currentBlocks.length, "text");
    }

    function requestDeleteBlock(blockId: string) {
        // Check if user has suppressed the confirmation
        const suppressed =
            localStorage.getItem("sushi:confirmDelete") === "true";
        if (suppressed) {
            executeDeleteBlock(blockId);
        } else {
            pendingDeleteBlockId = blockId;
            confirmDeleteOpen = true;
        }
    }

    function executeDeleteBlock(blockId: string) {
        currentBlocks = currentBlocks.filter((b) => b.blockId !== blockId);
        delete blockContents[blockId];
        confirmDeleteOpen = false;
        pendingDeleteBlockId = null;
        hoveredBlockId = null;

        // Re-render and save
        showBlocks = false;
        queueMicrotask(() => {
            showBlocks = true;
        });
        triggerSave();
    }

    function moveBlock(blockId: string, direction: "up" | "down") {
        const idx = currentBlocks.findIndex((b) => b.blockId === blockId);
        if (idx < 0) return;

        const targetIdx = direction === "up" ? idx - 1 : idx + 1;
        if (targetIdx < 0 || targetIdx >= currentBlocks.length) return;

        // Swap
        const copy = [...currentBlocks];
        [copy[idx], copy[targetIdx]] = [copy[targetIdx], copy[idx]];
        currentBlocks = copy;

        // Re-render and save
        showBlocks = false;
        queueMicrotask(() => {
            showBlocks = true;
        });
        triggerSave();
    }
</script>

<div class="h-screen flex-grow bg-neutral-900 flex flex-col font-mono">
    <!-- Editor Toolbar -->
    <div class="h-12 border-b border-neutral-800 flex items-center px-6 gap-2">
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
            onclick={() => ($isLeftPanelOpen = !$isLeftPanelOpen)}
            title={$isLeftPanelOpen ? "Close Explorer" : "Open Explorer"}
        >
            {#if $isLeftPanelOpen}
                <PanelLeftClose size={16} />
            {:else}
                <PanelLeftOpen size={16} />
            {/if}
        </button>
        <div class="w-px h-4 bg-neutral-800 mx-1"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Bold size={16} />
        </button>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Italic size={16} />
        </button>
        <div class="w-px h-4 bg-neutral-800 mx-1"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <List size={16} />
        </button>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Link size={16} />
        </button>

        <div class="flex-grow"></div>
        {#if $isSavingNote}
            <span class="text-xs text-yellow-500 flex items-center gap-1">
                <Loader2 size={12} class="animate-spin" />
                Saving...
            </span>
        {:else if $activeNoteContent}
            <span class="text-xs text-neutral-600">Saved</span>
        {/if}

        <div class="w-px h-4 bg-neutral-800 mx-2"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
            onclick={() => ($isRightPanelOpen = !$isRightPanelOpen)}
            title={$isRightPanelOpen
                ? "Close Details Panel"
                : "Open Details Panel"}
        >
            {#if $isRightPanelOpen}
                <PanelRightClose size={16} />
            {:else}
                <PanelRightOpen size={16} />
            {/if}
        </button>
    </div>

    <!-- Editor Content -->
    <div class="flex-grow overflow-y-auto p-12 max-w-4xl mx-auto w-full">
        {#if $isLoadingNote}
            <div class="flex items-center justify-center h-64 text-neutral-500">
                <Loader2 size={32} class="animate-spin" />
            </div>
        {:else if !$activeNoteId}
            <!-- No note selected — branded home -->
            <div
                class="flex flex-col items-center justify-center h-full text-neutral-500 gap-4"
            >
                <img
                    src="/logo2.png"
                    alt="Sushi"
                    class="w-20 h-20 object-contain opacity-40"
                />
                <p class="text-lg font-semibold text-neutral-400">Sushi</p>
                <p class="text-sm">
                    Select a note from the sidebar or create a new one
                </p>
            </div>
        {:else if showBlocks && initializedNoteId}
            <!-- Key on initializedNoteId to force full re-render when note changes -->
            {#key initializedNoteId}
                <!-- Title -->
                <textarea
                    class="text-4xl font-bold text-neutral-100 mb-8 outline-none bg-transparent w-full placeholder:text-neutral-600 resize-none overflow-hidden h-auto block"
                    maxlength="256"
                    rows="1"
                    placeholder="Untitled Note"
                    value={currentTitle}
                    oninput={handleTitleInput}
                    onkeydown={(e) => {
                        if (e.key === "Enter") {
                            e.preventDefault();
                            const firstBlock =
                                document.querySelector(".editor-block");
                            if (firstBlock instanceof HTMLElement) {
                                firstBlock.focus();
                            }
                        }
                    }}
                ></textarea>

                <!-- Blocks -->
                <div class="blocks-container">
                    {#if currentBlocks.length === 0}
                        <GhostBlock onadd={appendBlock} />
                    {:else}
                        {#each currentBlocks as block, i (block.blockId)}
                            <!-- Inserter between blocks -->
                            {#if i > 0}
                                <BlockInserter
                                    oninsert={(type: string) =>
                                        insertBlockAt(i, type)}
                                />
                            {/if}

                            <!-- Block wrapper with toolbar -->
                            <!-- svelte-ignore a11y_no_static_element_interactions -->
                            <div
                                class="block-wrapper"
                                class:block-hovered={hoveredBlockId ===
                                    block.blockId}
                                onmouseenter={() =>
                                    (hoveredBlockId = block.blockId)}
                                onmouseleave={() => (hoveredBlockId = null)}
                            >
                                <BlockToolbar
                                    visible={hoveredBlockId === block.blockId}
                                    isFirst={i === 0}
                                    isLast={i === currentBlocks.length - 1}
                                    ondelete={() =>
                                        requestDeleteBlock(block.blockId)}
                                    onmoveup={() =>
                                        moveBlock(block.blockId, "up")}
                                    onmovedown={() =>
                                        moveBlock(block.blockId, "down")}
                                />

                                {#if block.type === "text"}
                                    <div
                                        class="editor-block text-neutral-300 outline-none p-3 whitespace-pre-wrap"
                                        contenteditable="true"
                                        data-block-id={block.blockId}
                                        use:initContent={block.blockId}
                                        oninput={(e) =>
                                            handleBlockInput(block.blockId, e)}
                                    ></div>
                                {:else if block.type === "code"}
                                    <pre
                                        class="editor-block bg-neutral-800/60 text-neutral-300 p-3 rounded-b text-sm overflow-x-auto outline-none"
                                        contenteditable="true"
                                        data-block-id={block.blockId}
                                        use:initContent={block.blockId}
                                        oninput={(e) =>
                                            handleBlockInput(
                                                block.blockId,
                                                e,
                                            )}></pre>
                                {:else if block.type === "todo"}
                                    <div class="flex items-center gap-2 p-3">
                                        <input
                                            type="checkbox"
                                            checked={block.data?.checked ||
                                                false}
                                            class="accent-orange-500"
                                        />
                                        <div
                                            class="editor-block text-neutral-300 outline-none flex-1"
                                            contenteditable="true"
                                            data-block-id={block.blockId}
                                            use:initContent={block.blockId}
                                            oninput={(e) =>
                                                handleBlockInput(
                                                    block.blockId,
                                                    e,
                                                )}
                                        ></div>
                                    </div>
                                {:else}
                                    <div
                                        class="editor-block text-neutral-300 outline-none p-3 whitespace-pre-wrap"
                                        contenteditable="true"
                                        data-block-id={block.blockId}
                                        use:initContent={block.blockId}
                                        oninput={(e) =>
                                            handleBlockInput(block.blockId, e)}
                                    ></div>
                                {/if}
                            </div>
                        {/each}

                        <!-- Inserter after last block + ghost block -->
                        <BlockInserter
                            oninsert={(type: string) =>
                                insertBlockAt(currentBlocks.length, type)}
                        />
                        <GhostBlock onadd={appendBlock} />
                    {/if}
                </div>
            {/key}
        {:else}
            <div class="text-neutral-500 text-center py-8">Loading note...</div>
        {/if}
    </div>
</div>

<!-- Delete confirmation dialog -->
<ConfirmDialog
    open={confirmDeleteOpen}
    title="Delete Block"
    message="Are you sure you want to delete this block? This action cannot be undone."
    confirmLabel="Delete"
    localStorageKey="sushi:confirmDelete"
    onconfirm={() => {
        if (pendingDeleteBlockId) {
            executeDeleteBlock(pendingDeleteBlockId);
        }
    }}
    oncancel={() => {
        confirmDeleteOpen = false;
        pendingDeleteBlockId = null;
    }}
/>

<style>
    .blocks-container {
        display: flex;
        flex-direction: column;
    }

    .block-wrapper {
        position: relative;
        border: 1px solid transparent;
        border-radius: 8px;
        transition: border-color 0.15s ease;
    }

    .block-wrapper.block-hovered {
        border-color: #404040;
    }
</style>
