<script lang="ts">
    import {
        ChevronRight,
        ChevronDown,
        Folder,
        FileText,
        Loader2,
    } from "lucide-svelte";
    import {
        getDirectoryContents,
        deleteDirectoryByPath,
        moveItem,
        moveNoteById,
        createDirectoryIn,
        renameNoteById,
        renameDirectoryByPath,
    } from "$lib/client/apiClient";
    import type { DirectoryItem, NoteListItem } from "$lib/client/_apiTypes";
    import {
        loadNote,
        activeNoteId,
        createAndOpenNote,
        deleteNoteAction,
        duplicateNoteAction,
    } from "$lib/stores/notesStore";
    import { addToast } from "$lib/stores/toastStore";
    import {
        expandedDirs,
        toggleDir,
        expandDir,
        treeVersion,
        selectedDirPath,
    } from "$lib/stores/fileTreeStore";
    import { refreshTree } from "$lib/stores/fileTreeStore";
    import { dragItem, dragOverDir, startDrag } from "$lib/stores/dragStore";
    import ContextMenu from "../ContextMenu.svelte";
    import ConfirmDialog from "../ConfirmDialog.svelte";
    import FileTreeNode from "./FileTreeNode.svelte";

    interface Props {
        path: string | null;
        name: string;
        isRoot?: boolean;
    }

    let { path, name, isRoot = false }: Props = $props();

    // Stable key for this directory in the expanded-dirs store
    let dirKey = $derived(isRoot ? "__root__" : (path ?? "__root__"));

    let isLoading = $state(false);
    let isLoaded = $state(false);
    let subdirs = $state<DirectoryItem[]>([]);
    let notes = $state<NoteListItem[]>([]);

    // Context menu state
    let contextMenu = $state<{
        x: number;
        y: number;
        type: "note" | "dir" | "empty";
        noteId?: string;
        notePath?: string;
        dirPath?: string;
    } | null>(null);

    // Confirm dialog state
    let confirmDelete = $state<{
        open: boolean;
        itemType: "note" | "dir";
        itemId: string;
        itemName: string;
    }>({ open: false, itemType: "note", itemId: "", itemName: "" });

    // Rename state
    let renamingItem = $state<{
        type: "note" | "dir";
        id: string; // noteId or dirPath
        value: string; // current edit value
    } | null>(null);
    let renameInputRef: HTMLInputElement | null = null;

    // Drag-and-drop state (mouse-based, not HTML5 DnD)
    let dragHoverTimer: ReturnType<typeof setTimeout> | null = null;
    let isDropTarget = $derived($dragOverDir === dirKey);

    // Derive expanded state from the persistent store
    let isExpanded = $derived($expandedDirs.has(dirKey));
    let isSelected = $derived($selectedDirPath === path);

    // ========== Reactive Refresh ==========
    // When treeVersion changes, re-fetch contents for expanded/loaded nodes
    $effect(() => {
        const _v = $treeVersion; // subscribe to version changes
        if (isLoaded && isExpanded) {
            fetchContents();
        }
    });

    async function fetchContents() {
        isLoading = true;
        try {
            const contents = await getDirectoryContents(path);
            subdirs = contents.subdirs;
            notes = contents.notes;
            isLoaded = true;
        } catch (error) {
            console.error("Failed to load directory contents:", error);
            addToast("error", `Failed to load ${name}`);
        } finally {
            isLoading = false;
        }
    }

    function handleToggle() {
        // Set this directory as selected
        selectedDirPath.set(path);

        if (!isExpanded && !isLoaded) {
            fetchContents().then(() => toggleDir(dirKey));
        } else {
            toggleDir(dirKey);
        }
    }

    function handleNoteClick(noteId: string) {
        loadNote(noteId);
    }

    function handleDirSelect(e: MouseEvent) {
        // When clicking a directory, also select it
        selectedDirPath.set(path);
    }

    // ========== Context Menu ==========

    function handleDirContextMenu(e: MouseEvent) {
        e.preventDefault();
        e.stopPropagation();
        contextMenu = {
            x: e.clientX,
            y: e.clientY,
            type: "dir",
            dirPath: path ?? undefined,
        };
    }

    function handleNoteContextMenu(
        e: MouseEvent,
        noteId: string,
        noteTitle: string,
    ) {
        e.preventDefault();
        e.stopPropagation();
        contextMenu = {
            x: e.clientX,
            y: e.clientY,
            type: "note",
            noteId,
        };
    }

    function handleEmptyAreaContextMenu(e: MouseEvent) {
        e.preventDefault();
        contextMenu = {
            x: e.clientX,
            y: e.clientY,
            type: "empty",
        };
    }

    function getContextMenuItems() {
        if (!contextMenu) return [];

        if (contextMenu.type === "note") {
            return [
                {
                    label: "Rename",
                    icon: "✏️",
                    action: () => {
                        if (contextMenu?.noteId) {
                            const noteTitle =
                                notes.find(
                                    (n) => n.noteId === contextMenu!.noteId,
                                )?.noteTitle ?? "";
                            startRename("note", contextMenu.noteId, noteTitle);
                        }
                    },
                },
                {
                    label: "Duplicate",
                    icon: "📋",
                    action: () => {
                        if (contextMenu?.noteId)
                            duplicateNoteAction(contextMenu.noteId);
                    },
                },
                {
                    label: "Delete",
                    icon: "🗑",
                    action: () => {
                        if (contextMenu?.noteId) {
                            const noteTitle =
                                notes.find(
                                    (n) => n.noteId === contextMenu!.noteId,
                                )?.noteTitle ?? "this note";
                            confirmDelete = {
                                open: true,
                                itemType: "note",
                                itemId: contextMenu.noteId,
                                itemName: noteTitle,
                            };
                        }
                    },
                    danger: true,
                },
            ];
        }

        if (contextMenu.type === "dir") {
            return [
                {
                    label: "New Note Here",
                    icon: "📄",
                    action: () => {
                        createAndOpenNote(
                            "Untitled Note",
                            contextMenu?.dirPath ?? path,
                        );
                    },
                },
                {
                    label: "New Folder Here",
                    icon: "📁",
                    action: () => {
                        handleCreateSubfolder(
                            contextMenu?.dirPath ?? path ?? undefined,
                        );
                    },
                },
                {
                    label: "Rename",
                    icon: "✏️",
                    action: () => {
                        if (contextMenu?.dirPath) {
                            const dirName =
                                contextMenu.dirPath.split(/[\\/]/).pop() ?? "";
                            startRename("dir", contextMenu.dirPath, dirName);
                        }
                    },
                },
                {
                    label: "Delete Folder",
                    icon: "🗑",
                    action: () => {
                        if (contextMenu?.dirPath) {
                            confirmDelete = {
                                open: true,
                                itemType: "dir",
                                itemId: contextMenu.dirPath,
                                itemName: name,
                            };
                        }
                    },
                    danger: true,
                },
            ];
        }

        // Empty area
        return [
            {
                label: "New Note",
                icon: "📄",
                action: () => {
                    createAndOpenNote("Untitled Note", path);
                },
            },
            {
                label: "New Folder",
                icon: "📁",
                action: () => {
                    handleCreateSubfolder(path ?? undefined);
                },
            },
        ];
    }

    async function handleCreateSubfolder(parentPath?: string) {
        const folderName = prompt("Folder name:");
        if (!folderName || !folderName.trim()) return;

        try {
            const result = await createDirectoryIn(
                parentPath ?? "",
                folderName.trim(),
            );
            if (result.success) {
                refreshTree();
                addToast("success", `Created folder "${folderName.trim()}"`);
            } else {
                addToast("error", result.message || "Failed to create folder");
            }
        } catch (error) {
            console.error("Failed to create folder:", error);
            addToast("error", "Failed to create folder");
        }
    }

    async function handleConfirmDelete() {
        confirmDelete.open = false;
        if (confirmDelete.itemType === "note") {
            await deleteNoteAction(confirmDelete.itemId);
        } else {
            try {
                const result = await deleteDirectoryByPath(
                    confirmDelete.itemId,
                );
                if (result.success) {
                    refreshTree();
                    addToast("success", "Folder deleted");
                } else {
                    addToast(
                        "error",
                        result.message || "Failed to delete folder",
                    );
                }
            } catch (error) {
                console.error("Failed to delete directory:", error);
                addToast("error", "Failed to delete folder");
            }
        }
    }

    // ========== Rename ==========

    function startRename(
        type: "note" | "dir",
        id: string,
        currentName: string,
    ) {
        renamingItem = { type, id, value: currentName };
        // Focus the input after Svelte renders it
        requestAnimationFrame(() => {
            renameInputRef?.focus();
            renameInputRef?.select();
        });
    }

    async function commitRename() {
        if (!renamingItem) return;
        const { type, id, value } = renamingItem;
        const trimmed = value.trim();
        if (!trimmed) {
            renamingItem = null;
            return;
        }

        try {
            let result;
            if (type === "note") {
                result = await renameNoteById(id, trimmed);
            } else {
                result = await renameDirectoryByPath(id, trimmed);
            }

            if (result.success) {
                // Delay refresh to let watcher process rename
                setTimeout(() => refreshTree(), 400);
                addToast("success", `Renamed to "${trimmed}"`);
            } else {
                addToast("error", result.message || "Rename failed");
            }
        } catch (error) {
            console.error("Rename failed:", error);
            addToast("error", "Rename failed");
        }

        renamingItem = null;
    }

    function cancelRename() {
        renamingItem = null;
    }

    function handleRenameKeydown(e: KeyboardEvent) {
        if (e.key === "Enter") {
            e.preventDefault();
            commitRename();
        } else if (e.key === "Escape") {
            e.preventDefault();
            cancelRename();
        }
    }

    // ========== Drag and Drop (Mouse-based) ==========
    // HTML5 DnD is blocked by WebView2 on Windows (red circle/slash).
    // We use mousedown to initiate drag, mouseenter/mouseleave for hover.

    function handleMouseDownDrag(
        e: MouseEvent,
        itemId: string,
        itemType: "note" | "dir",
        itemName: string,
    ) {
        // Only left mouse button
        if (e.button !== 0) return;
        startDrag({ id: itemId, type: itemType, name: itemName }, e);
    }

    function handleDirMouseEnter() {
        if (!$dragItem) return;
        dragOverDir.set(dirKey);
        // Auto-expand after 600ms hover
        dragHoverTimer = setTimeout(() => {
            if (!isExpanded) {
                if (!isLoaded) {
                    fetchContents().then(() => expandDir(dirKey));
                } else {
                    expandDir(dirKey);
                }
            }
        }, 600);
    }

    function handleDirMouseLeave() {
        if ($dragOverDir === dirKey) {
            dragOverDir.set(null);
        }
        if (dragHoverTimer) {
            clearTimeout(dragHoverTimer);
            dragHoverTimer = null;
        }
    }

    // Auto-load root on mount
    $effect(() => {
        if (isRoot && !isLoaded) {
            fetchContents();
        }
    });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="select-none">
    <!-- Directory Header -->
    {#if !isRoot}
        <button
            class="dir-row"
            class:dir-selected={isSelected}
            class:drag-over={isDropTarget}
            onclick={handleToggle}
            oncontextmenu={handleDirContextMenu}
            onmousedown={(e) => handleMouseDownDrag(e, path ?? "", "dir", name)}
            onmouseenter={handleDirMouseEnter}
            onmouseleave={handleDirMouseLeave}
        >
            {#if isLoading}
                <Loader2 size={14} class="animate-spin flex-shrink-0" />
            {:else if isExpanded}
                <ChevronDown size={14} class="flex-shrink-0" />
            {:else}
                <ChevronRight size={14} class="flex-shrink-0" />
            {/if}
            <Folder size={14} class="flex-shrink-0 text-yellow-500/70" />
            {#if renamingItem?.type === "dir" && renamingItem?.id === path}
                <input
                    bind:this={renameInputRef}
                    class="rename-input"
                    type="text"
                    bind:value={renamingItem.value}
                    onkeydown={handleRenameKeydown}
                    onblur={commitRename}
                />
            {:else}
                <span class="truncate">{name}</span>
            {/if}
        </button>
    {:else}
        <!-- Root drop target (invisible) -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class:drag-over-root={isDropTarget}
            onmouseenter={handleDirMouseEnter}
            onmouseleave={handleDirMouseLeave}
        ></div>
    {/if}

    <!-- Contents (subdirs + notes) -->
    {#if isExpanded || isRoot}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class={isRoot ? "tree-root" : "pl-4"}
            class:drag-over-root={isRoot && isDropTarget && !!$dragItem}
            oncontextmenu={isRoot ? handleEmptyAreaContextMenu : undefined}
            onmouseover={isRoot
                ? (e) => {
                      if (!$dragItem) return;
                      // When mouse is directly over the tree area (not over a child node),
                      // set root as the drop target. This recaptures root when leaving a subfolder.
                      if (
                          e.target === e.currentTarget ||
                          !(e.target as HTMLElement).closest(".dir-row")
                      ) {
                          dragOverDir.set(dirKey);
                      }
                  }
                : undefined}
        >
            {#if isLoading && isRoot && !isLoaded}
                <div
                    class="flex items-center justify-center py-4 text-neutral-500"
                >
                    <Loader2 size={18} class="animate-spin" />
                </div>
            {:else}
                <!-- Subdirectories -->
                {#each subdirs as dir (dir.dirPath)}
                    <FileTreeNode path={dir.dirPath} name={dir.dirName} />
                {/each}

                <!-- Notes -->
                {#each notes as note (note.noteId)}
                    <button
                        class="note-row"
                        class:note-active={$activeNoteId === note.noteId}
                        onclick={() => handleNoteClick(note.noteId)}
                        oncontextmenu={(e) =>
                            handleNoteContextMenu(
                                e,
                                note.noteId,
                                note.noteTitle,
                            )}
                        onmousedown={(e) =>
                            handleMouseDownDrag(
                                e,
                                note.noteId,
                                "note",
                                note.noteTitle,
                            )}
                    >
                        <FileText size={14} class="flex-shrink-0" />
                        {#if renamingItem?.type === "note" && renamingItem?.id === note.noteId}
                            <input
                                bind:this={renameInputRef}
                                class="rename-input"
                                type="text"
                                bind:value={renamingItem.value}
                                onkeydown={handleRenameKeydown}
                                onblur={commitRename}
                            />
                        {:else}
                            <span class="truncate">{note.noteTitle}</span>
                        {/if}
                    </button>
                {/each}

                <!-- Empty state -->
                {#if isLoaded && subdirs.length === 0 && notes.length === 0}
                    <div class="text-xs text-neutral-600 px-2 py-1 italic">
                        Empty folder
                    </div>
                {/if}
            {/if}
        </div>
    {/if}
</div>

<!-- Context Menu -->
{#if contextMenu}
    <ContextMenu
        x={contextMenu.x}
        y={contextMenu.y}
        items={getContextMenuItems()}
        onclose={() => (contextMenu = null)}
    />
{/if}

<!-- Confirm Delete Dialog -->
<ConfirmDialog
    open={confirmDelete.open}
    title={confirmDelete.itemType === "note" ? "Delete Note" : "Delete Folder"}
    message={`Are you sure you want to delete "${confirmDelete.itemName}"?${confirmDelete.itemType === "dir" ? " This will also delete all contents inside." : ""}`}
    confirmLabel="Delete"
    localStorageKey={confirmDelete.itemType === "note"
        ? "skip-confirm-delete-note"
        : "skip-confirm-delete-dir"}
    onconfirm={handleConfirmDelete}
    oncancel={() => {
        confirmDelete.open = false;
    }}
/>

<style>
    .dir-row {
        width: 100%;
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 0.875rem;
        color: #a3a3a3;
        padding: 4px 8px;
        border-radius: 4px;
        cursor: pointer;
        text-align: left;
        border: 1px solid transparent;
        background: none;
        transition: all 0.1s ease;
    }

    .dir-row:hover {
        background: #262626;
        color: #e5e5e5;
    }

    .dir-row.dir-selected {
        background: #262626;
        color: #e5e5e5;
    }

    .dir-row.drag-over {
        border-color: #f97316;
        background: rgba(249, 115, 22, 0.08);
    }

    .drag-over-root {
        border: 1px dashed #f97316;
        border-radius: 4px;
    }

    .note-row {
        width: 100%;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.875rem;
        color: #a3a3a3;
        padding: 4px 8px;
        border-radius: 4px;
        cursor: pointer;
        text-align: left;
        border: none;
        background: none;
        transition: all 0.1s ease;
    }

    .note-row:hover {
        background: #262626;
        color: #e5e5e5;
    }

    .note-row.note-active {
        background: #262626;
        color: #f5f5f5;
    }

    .rename-input {
        flex: 1;
        min-width: 0;
        background: #1a1a1a;
        border: 1px solid #f97316;
        border-radius: 3px;
        padding: 1px 4px;
        font-size: 0.875rem;
        color: #f5f5f5;
        outline: none;
    }

    .tree-root {
        min-height: 100px;
    }

    :global(.pl-4) {
        padding-left: 1rem;
    }
</style>
