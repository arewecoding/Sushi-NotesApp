<script lang="ts">
    /**
     * MainArea.svelte
     * ================
     * The core note editor component. Manages the note title, block list,
     * toolbar formatting dispatch, block CRUD operations (create, delete,
     * move, reorder), and content synchronisation with the backend via
     * debounced saves. Uses non-reactive plain JS (blockContents) for
     * editing performance, syncing to Svelte stores only on save.
     */
    import {
        Bold,
        Italic,
        List,
        Strikethrough,
        Code,
        Quote,
        Minus,
        Heading1,
        Heading2,
        Heading3,
        PanelRightOpen,
        PanelRightClose,
        PanelLeftOpen,
        PanelLeftClose,
        Loader2,
    } from "lucide-svelte";
    import { isRightPanelOpen, isLeftPanelOpen } from "$lib/stores/layoutStore";
    import {
        activeNoteContent,
        isLoadingNote,
        activeNoteId,
        isSavingNote,
        saveNoteContentDebounced,
        noteContentVersion,
        notesList,
        loadNote,
    } from "$lib/stores/notesStore";
    import type { NoteBlock } from "$lib/client/_apiTypes";
    import BlockToolbar from "$lib/components/editor/BlockToolbar.svelte";
    import BlockInserter from "$lib/components/editor/BlockInserter.svelte";
    import GhostBlock from "$lib/components/editor/GhostBlock.svelte";
    import RichTextBlock from "$lib/components/editor/RichTextBlock.svelte";
    import LaTeXBlock from "$lib/components/editor/LaTeXBlock.svelte";
    import CodeBlock from "$lib/components/editor/CodeBlock.svelte";
    import LinkModal from "$lib/components/linking/LinkModal.svelte";
    import ConfirmDialog from "$lib/components/ConfirmDialog.svelte";
    import { openLinkModal } from "$lib/stores/linkModalStore";
    import {
        FOCUS_BLUR_DELAY_MS,
        NAVIGATE_SCROLL_DELAY_MS,
        latexSnippets,
    } from "$lib/editor/editorConstants";
    import { createBlockCmd } from "$lib/client/apiClient";
    import {
        dragBlockIndex,
        dropTargetIndex,
        isBlockDragging,
        startBlockDrag,
        updateDropTarget,
        endBlockDrag,
    } from "$lib/stores/blockDragStore";
    import { currentView } from "$lib/stores/viewStore";
    import InfiniteCanvas from "$lib/components/canvas/InfiniteCanvas.svelte";
    import NotebookCanvasPlaceholder from "$lib/components/canvas/NotebookCanvasPlaceholder.svelte";
    import CanvasBlock from "$lib/components/editor/CanvasBlock.svelte";

    // Track which note and version we've initialized for
    let initializedNoteId: string | null = null;
    let lastInitializedVersion: number = 0;

    // ── Non-reactive block contents ────────────────────────────────────────
    // This is PLAIN JS - not $state() - so mutations don't trigger re-renders
    let blockContents: Record<string, string> = {};
    let blockLanguages: Record<string, string> = {};
    let currentTitle: string = "";
    let currentBlocks: NoteBlock[] = $state([]);

    // Reactive flag to show blocks (but content is managed non-reactively)
    let showBlocks = $state(false);

    // Block interaction state
    let hoveredBlockId = $state<string | null>(null);
    let confirmDeleteOpen = $state(false);
    let pendingDeleteBlockId = $state<string | null>(null);

    // ── Context-aware toolbar ──────────────────────────────────────────────
    /** The block that currently has keyboard focus */
    let focusedBlock = $state<{ id: string; type: string } | null>(null);

    /** Component refs — keyed by blockId */
    let blockRefs: Record<
        string,
        {
            applyFormat?: (t: string) => void;
            insertSnippet?: (t: string) => void;
            insertLinkSyntax?: (s: string) => void;
            replaceSelectionWithLink?: (s: string) => void;
            getSelectedText?: () => string;
        } | null
    > = {};

    function handleBlockFocusIn(blockId: string, blockType: string) {
        focusedBlock = { id: blockId, type: blockType };
    }

    function handleBlockFocusOut() {
        // Small delay so clicking a toolbar button doesn't clear focusedBlock
        // before the button's onclick fires
        setTimeout(() => {
            // Only clear if nothing inside the editor area is newly focused
            if (!document.activeElement?.closest(".editor-content-area")) {
                focusedBlock = null;
            }
        }, FOCUS_BLUR_DELAY_MS);
    }

    /** Dispatch a format action to the currently focused text/todo block */
    function toolbarFormat(type: string) {
        if (!focusedBlock) return;
        const ref = blockRefs[focusedBlock.id];
        ref?.applyFormat?.(type);
    }

    /** Insert a LaTeX snippet into the currently focused latex block */
    function toolbarLatex(snippet: string) {
        if (!focusedBlock) return;
        const ref = blockRefs[focusedBlock.id];
        ref?.insertSnippet?.(snippet);
    }

    /**
     * Called by RichTextBlock when user types `[[`.
     * Opens the link modal with a callback to insert at cursor.
     */
    function handleLinkStart(blockId: string) {
        const ref = blockRefs[blockId];
        openLinkModal({
            displayText: "",
            blockId,
            insertionCallback: (syntax: string) => {
                ref?.insertLinkSyntax?.(syntax);
            },
        });
    }

    /**
     * Toolbar Link button — opens the link modal with the
     * current selection text, if any.
     */
    function handleToolbarLink() {
        if (!focusedBlock) return;
        const ref = blockRefs[focusedBlock.id];
        const selectedText = ref?.getSelectedText?.() ?? "";
        const blockId = focusedBlock.id;

        openLinkModal({
            displayText: selectedText,
            blockId,
            insertionCallback: (syntax: string) => {
                if (selectedText) {
                    // Replace selection with pill syntax (Issue 4)
                    ref?.replaceSelectionWithLink?.(syntax);
                } else {
                    // Insert at cursor
                    ref?.insertLinkSyntax?.(syntax);
                }
            },
        });
    }

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

                // Build content and language maps for blocks
                blockContents = {};
                blockLanguages = {};
                for (const block of content.blocks) {
                    blockContents[block.blockId] =
                        block.data?.content || block.data?.code || "";
                    if (block.type === "code") {
                        blockLanguages[block.blockId] =
                            (block.data?.language as string) || "plaintext";
                    }
                }

                // Trigger re-render to show the new blocks
                rerenderBlocks();
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
        blockContents[blockId] = target.innerText || "";
        triggerSave();
    }

    /** Called by LinkedBlock's onchange — receives plain text with [[links]] preserved. */
    function handleLinkedBlockChange(blockId: string, text: string) {
        blockContents[blockId] = text;
        triggerSave();
    }

    /** Called by CodeBlock on content change. */
    function handleCodeBlockChange(blockId: string, code: string) {
        blockContents[blockId] = code;
        triggerSave();
    }

    /** Called by CodeBlock when the user changes the language. */
    function handleCodeLanguageChange(blockId: string, lang: string) {
        blockLanguages[blockId] = lang;
        // Also update the block's data directly so triggerSave picks it up
        const block = currentBlocks.find((b) => b.blockId === blockId);
        if (block) {
            block.data = { ...block.data, language: lang };
        }
        triggerSave();
    }

    /** Called by CodeBlock when user presses Escape to exit the block. */
    function handleCodeBlockEscape(blockId: string) {
        // Move focus to the block wrapper so keyboard navigation works
        const wrapper = document.querySelector(
            `[data-block-id="${blockId}"]`,
        )?.closest(".block-wrapper");
        if (wrapper instanceof HTMLElement) {
            wrapper.focus();
        }
    }

    /**
     * Called by CanvasBlock on blur/save — updates block data and triggers note save.
     * The data arg carries { canvas_ref, thumbnail_ref, size } from the block.
     */
    function handleCanvasBlockChange(blockId: string, newData: object) {
        // SAFETY: ignore stale change callbacks from a previous note's CanvasBlock
        if ($activeNoteId !== initializedNoteId) return;

        const block = currentBlocks.find((b) => b.blockId === blockId);
        if (block) {
            block.data = { ...block.data, ...newData };
        }
        triggerSave();
    }

    /** Navigate to a linked note (and optionally scroll to a block). */
    async function handleNavigate(noteId: string, blockId: string | null) {
        await loadNote(noteId);
        if (blockId) {
            // Wait for DOM then scroll to block
            await new Promise((r) => setTimeout(r, NAVIGATE_SCROLL_DELAY_MS));
            const el = document.querySelector(`[data-block-id="${blockId}"]`);
            if (el instanceof HTMLElement) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                el.focus();
            }
        }
    }

    function triggerSave() {
        if (!initializedNoteId) return;
        
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
                ...(block.type === "code"
                    ? { language: blockLanguages[block.blockId] || "plaintext" }
                    : {}),
            },
        }));
        saveNoteContentDebounced(initializedNoteId, currentTitle, blocksToSave);
    }

    // ========== Block Operations ==========

    /** Force a Svelte re-render of the block list via a destroy/recreate cycle. */
    function rerenderBlocks() {
        showBlocks = false;
        queueMicrotask(() => {
            showBlocks = true;
        });
    }

    async function insertBlockAt(index: number, type: string = "text") {
        if (!$activeNoteId) return;
        
        const newBlock = await createBlockCmd($activeNoteId, type);
        if (!newBlock) return;

        currentBlocks = [
            ...currentBlocks.slice(0, index),
            newBlock,
            ...currentBlocks.slice(index),
        ];
        blockContents[newBlock.blockId] = "";

        // Let the keyed {#each} handle the surgical DOM insert — no rerenderBlocks()
        queueMicrotask(() => {
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

        // Keyed {#each} handles DOM removal surgically — no rerenderBlocks()
        triggerSave();
    }

    function moveBlock(blockId: string, direction: "up" | "down") {
        const idx = currentBlocks.findIndex((b) => b.blockId === blockId);
        if (idx < 0) return;

        const targetIdx = direction === "up" ? idx - 1 : idx + 1;
        if (targetIdx < 0 || targetIdx >= currentBlocks.length) return;

        const copy = [...currentBlocks];
        [copy[idx], copy[targetIdx]] = [copy[targetIdx], copy[idx]];
        currentBlocks = copy;

        triggerSave();
    }

    function reorderBlock(fromIndex: number, toIndex: number) {
        if (fromIndex === toIndex) return;
        const copy = [...currentBlocks];
        const [moved] = copy.splice(fromIndex, 1);
        copy.splice(toIndex, 0, moved);
        currentBlocks = copy;

        triggerSave();
    }

    function handleBlockMouseUp() {
        const result = endBlockDrag();
        if (result) {
            const [from, to] = result;
            reorderBlock(from, to);
        }
    }
</script>

<svelte:window onmouseup={handleBlockMouseUp} />

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

        {#if focusedBlock?.type === "text" || focusedBlock?.type === "todo"}
            <!-- ── Text / Markdown toolbar ── -->
            <button
                class="toolbar-fmt-btn"
                title="Bold (wraps selection)"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("bold");
                }}
            >
                <Bold size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Italic (wraps selection)"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("italic");
                }}
            >
                <Italic size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Strikethrough"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("strike");
                }}
            >
                <Strikethrough size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Inline code"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("code");
                }}
            >
                <Code size={14} />
            </button>
            <div class="w-px h-4 bg-neutral-800 mx-1"></div>
            <button
                class="toolbar-fmt-btn"
                title="Heading 1"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("h1");
                }}
            >
                <Heading1 size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Heading 2"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("h2");
                }}
            >
                <Heading2 size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Heading 3"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("h3");
                }}
            >
                <Heading3 size={14} />
            </button>
            <div class="w-px h-4 bg-neutral-800 mx-1"></div>
            <button
                class="toolbar-fmt-btn"
                title="Bullet list (new line)"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("list");
                }}
            >
                <List size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Blockquote"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("quote");
                }}
            >
                <Quote size={14} />
            </button>
            <button
                class="toolbar-fmt-btn"
                title="Horizontal rule"
                onmousedown={(e) => {
                    e.preventDefault();
                    toolbarFormat("hr");
                }}
            >
                <Minus size={14} />
            </button>
            <div class="w-px h-4 bg-neutral-800 mx-1"></div>
            <button
                class="toolbar-fmt-btn"
                title="Insert link ([[)"
                onmousedown={(e) => {
                    e.preventDefault();
                    handleToolbarLink();
                }}
            >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
            </button>
        {:else if focusedBlock?.type === "latex"}
            <!-- ── LaTeX toolbar ── -->
            <span
                class="text-[10px] font-semibold text-orange-500 font-mono tracking-widest mr-1"
                >LaTeX</span
            >
            <div class="w-px h-4 bg-neutral-800 mx-1"></div>
            {#each latexSnippets as item}
                {#if item.sep}
                    <div class="w-px h-4 bg-neutral-800 mx-1"></div>
                {:else}
                    <button
                        class="toolbar-fmt-btn font-mono text-xs"
                        title={item.title}
                        onmousedown={(e) => {
                            e.preventDefault();
                            toolbarLatex(item.snippet);
                        }}>{item.label}</button
                    >
                {/if}
            {/each}
        {:else}
            <!-- No block focused — subtle hint -->
            <span class="text-xs text-neutral-700 italic select-none"
                >Select a block to format</span
            >
        {/if}

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
    {#if $currentView.type === "canvas"}
        <div class="flex-grow flex flex-col overflow-hidden w-full h-full">
            <InfiniteCanvas canvasId={$currentView.canvasId} filePath={$currentView.filePath} />
        </div>
    {:else}
        <div class="flex-grow overflow-y-auto p-12 max-w-4xl mx-auto w-full editor-content-area">
            {#if $currentView.type === "book"}
                <NotebookCanvasPlaceholder bookId={$currentView.bookId} filePath={$currentView.filePath} />
            {:else if $isLoadingNote}
            <div class="flex items-center justify-center h-64 text-neutral-500">
                <Loader2 size={32} class="animate-spin" />
            </div>
        {:else if !$activeNoteId || $currentView.type === "empty"}
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
                <div
                    class="blocks-container"
                    class:block-dragging-active={$isBlockDragging}
                >
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

                            <!-- Block wrapper with toolbar and drag handle -->
                            <!-- svelte-ignore a11y_no_static_element_interactions -->
                            <div
                                class="block-wrapper"
                                class:block-hovered={hoveredBlockId ===
                                    block.blockId}
                                class:block-dragging={$isBlockDragging &&
                                    $dragBlockIndex === i}
                                class:block-drop-above={$isBlockDragging &&
                                    $dropTargetIndex === i &&
                                    $dragBlockIndex > i}
                                class:block-drop-below={$isBlockDragging &&
                                    $dropTargetIndex === i &&
                                    $dragBlockIndex < i}
                                onmouseenter={() => {
                                    hoveredBlockId = block.blockId;
                                    if ($isBlockDragging) updateDropTarget(i);
                                }}
                                onmouseleave={() => (hoveredBlockId = null)}
                                onfocusin={() =>
                                    handleBlockFocusIn(
                                        block.blockId,
                                        block.type,
                                    )}
                                onfocusout={handleBlockFocusOut}
                            >
                                <!-- Drag handle -->
                                <!-- svelte-ignore a11y_no_static_element_interactions -->
                                <div
                                    class="drag-handle"
                                    onmousedown={(e) => {
                                        e.preventDefault();
                                        if (e.button === 0) startBlockDrag(i);
                                    }}
                                    title="Hold to drag"
                                >
                                    <div class="handle-dots">
                                        <span></span><span></span><span></span>
                                        <span></span><span></span><span></span>
                                    </div>
                                </div>
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
                                    <!-- RichTextBlock: markdown + KaTeX + links, Typora-style edit -->
                                    <RichTextBlock
                                        bind:this={blockRefs[block.blockId]}
                                        blockId={block.blockId}
                                        initialContent={blockContents[
                                            block.blockId
                                        ] || ""}
                                        notesList={$notesList}
                                        className="text-neutral-300 p-3"
                                        onchange={handleLinkedBlockChange}
                                        onnavigate={handleNavigate}
                                        onlinkstart={handleLinkStart}
                                    />
                                {:else if block.type === "code"}
                                    <CodeBlock
                                        blockId={block.blockId}
                                        initialCode={blockContents[
                                            block.blockId
                                        ] || ""}
                                        initialLanguage={blockLanguages[
                                            block.blockId
                                        ] || "plaintext"}
                                        onchange={handleCodeBlockChange}
                                        onlanguagechange={handleCodeLanguageChange}
                                        onescape={handleCodeBlockEscape}
                                    />
                                {:else if block.type === "todo"}
                                    <div class="flex items-start gap-2 p-3">
                                        <input
                                            type="checkbox"
                                            checked={block.data?.checked ||
                                                false}
                                            class="accent-orange-500 mt-1 flex-shrink-0"
                                        />
                                        <RichTextBlock
                                            bind:this={blockRefs[block.blockId]}
                                            blockId={block.blockId}
                                            initialContent={blockContents[
                                                block.blockId
                                            ] || ""}
                                            notesList={$notesList}
                                            className="text-neutral-300 flex-1"
                                            onchange={handleLinkedBlockChange}
                                            onnavigate={handleNavigate}
                                            onlinkstart={handleLinkStart}
                                        />
                                    </div>
                                {:else if block.type === "latex"}
                                    <LaTeXBlock
                                        bind:this={blockRefs[block.blockId]}
                                        blockId={block.blockId}
                                        initialContent={blockContents[
                                            block.blockId
                                        ] || ""}
                                        className="p-1"
                                        onchange={handleLinkedBlockChange}
                                    />
                                {:else if block.type === "canvas"}
                                    <CanvasBlock
                                        blockId={block.blockId}
                                        noteId={initializedNoteId!}
                                        initialData={block.data as any}
                                        onchange={handleCanvasBlockChange}
                                    />
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
{/if}
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

<!-- Link modal -->
<LinkModal />

<style>
    /* Context-aware toolbar format buttons */
    .toolbar-fmt-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 26px;
        height: 26px;
        padding: 0 4px;
        border-radius: 4px;
        background: none;
        border: none;
        color: #9ca3af;
        cursor: pointer;
        transition:
            background 0.1s,
            color 0.1s;
        line-height: 1;
    }
    .toolbar-fmt-btn:hover {
        background: #2d2d2d;
        color: #f3f4f6;
    }
    .toolbar-fmt-btn:active {
        background: rgba(249, 115, 22, 0.15);
        color: #f97316;
    }

    .blocks-container {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    /* Prevent text selection while dragging blocks */
    :global(.block-dragging-active) {
        user-select: none !important;
        -webkit-user-select: none !important;
    }

    .block-wrapper {
        position: relative;
        border: 1px solid transparent;
        border-radius: 8px;
        transition:
            border-color 0.15s ease,
            margin 0.25s ease,
            opacity 0.2s ease;
        padding-left: 24px;
    }

    .block-wrapper.block-hovered {
        border-color: #404040;
    }

    /* Drag handle */
    .drag-handle {
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: grab;
        opacity: 0;
        transition: opacity 0.15s ease;
        border-radius: 4px 0 0 4px;
    }

    .block-wrapper.block-hovered .drag-handle,
    .block-wrapper:hover .drag-handle {
        opacity: 1;
    }

    .drag-handle:hover {
        background: #333;
    }

    .drag-handle:active {
        cursor: grabbing;
    }

    .handle-dots {
        display: grid;
        grid-template-columns: repeat(2, 4px);
        gap: 2px;
    }

    .handle-dots span {
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background: #666;
    }

    /* Dragging state */
    .block-wrapper.block-dragging {
        opacity: 0.35;
        border-color: #525252;
        border-style: dashed;
    }

    /* Drop target ghost placeholder — translucent orange box */
    .block-wrapper.block-drop-above {
        margin-top: 56px;
    }

    .block-wrapper.block-drop-above::before {
        content: "";
        position: absolute;
        left: 24px;
        right: 0;
        top: -52px;
        height: 48px;
        border: 2px dashed rgba(249, 115, 22, 0.6);
        border-radius: 8px;
        background: rgba(249, 115, 22, 0.06);
        pointer-events: none;
    }

    .block-wrapper.block-drop-below {
        margin-bottom: 56px;
    }

    .block-wrapper.block-drop-below::after {
        content: "";
        position: absolute;
        left: 24px;
        right: 0;
        bottom: -52px;
        height: 48px;
        border: 2px dashed rgba(249, 115, 22, 0.6);
        border-radius: 8px;
        background: rgba(249, 115, 22, 0.06);
        pointer-events: none;
    }
</style>
