<script lang="ts">
  /**
   * LeftPanel.svelte
   * ================
   * File explorer sidebar: header with New Note/Folder/Search buttons,
   * the FileTreeNode tree, right-click context menu, resizable width,
   * and mouse-based file drag-and-drop handling.
   */
  import { Plus, FolderPlus, Search } from "lucide-svelte";
  import {
    leftPanelWidth,
    isLeftPanelOpen,
    isSearchOpen,
  } from "$lib/stores/layoutStore";
  import { createAndOpenNote } from "$lib/stores/notesStore";
  import { refreshTree, selectedDirPath } from "$lib/stores/fileTreeStore";
  import {
    moveItem,
    moveNoteById,
    createDirectoryIn,
  } from "$lib/client/apiClient";
  import { addToast } from "$lib/stores/toastStore";
  import {
    dragItem,
    dragPosition,
    dragOverDir,
    updateDragPosition,
    endDrag,
  } from "$lib/stores/dragStore";
  import FileTreeNode from "./FileTreeNode.svelte";
  import ContextMenu from "../ContextMenu.svelte";
  import { listen } from "@tauri-apps/api/event";
  import { onMount } from "svelte";

  // Right-click context menu state
  let panelContextMenu = $state<{ x: number; y: number } | null>(null);

  function handlePanelContextMenu(e: MouseEvent) {
    e.preventDefault();
    panelContextMenu = { x: e.clientX, y: e.clientY };
  }

  let isDragging = false;

  function startDrag() {
    isDragging = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function stopDrag() {
    isDragging = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }

  function handleDrag(event: MouseEvent) {
    if (isDragging) {
      const newWidth = Math.max(200, Math.min(500, event.clientX));
      $leftPanelWidth = newWidth;
    }
    // Always call — handles both pending (threshold check) and active drag
    updateDragPosition(event);
  }

  function handleNewNote() {
    createAndOpenNote("Untitled Note", $selectedDirPath);
  }

  async function handleNewFolder() {
    const folderName = prompt("Folder name:");
    if (!folderName || !folderName.trim()) return;

    const parentPath = $selectedDirPath ?? "";
    try {
      const result = await createDirectoryIn(parentPath, folderName.trim());
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

  // Mouse-based drag-and-drop: handle drop on mouseup
  async function handleMouseUp() {
    // ALWAYS read state then clear — must clear hold timer even for quick clicks
    const item = $dragItem;
    const targetDir = $dragOverDir;
    endDrag(); // clears timer, cursor, and all drag state

    if (!item) return; // Quick click — no drag was active

    if (!targetDir) return; // Dropped outside any directory

    // Resolve the actual path for the target directory
    const destDir = targetDir === "__root__" ? "" : targetDir;

    try {
      let result;
      if (item.type === "note") {
        result = await moveNoteById(item.id, destDir);
      } else {
        if (item.id === destDir) return;
        result = await moveItem(item.id, destDir);
      }

      if (result.success) {
        refreshTree();
        addToast("success", "Moved successfully");
      } else {
        addToast("error", result.message || "Move failed");
      }
    } catch (error) {
      console.error("Drop failed:", error);
      addToast("error", "Move failed");
    }
  }

  // Listen for tree-changed events from backend
  onMount(() => {
    const unlisten = listen<{
      changed_path: string;
      event_type: string;
    }>("tree-changed", (event) => {
      console.log("Tree changed event received:", event.payload);
      refreshTree();
    });

    return () => {
      unlisten.then((fn) => fn());
    };
  });
</script>

<svelte:window
  onmousemove={handleDrag}
  onmouseup={(e) => {
    stopDrag();
    handleMouseUp();
  }}
/>

{#if $isLeftPanelOpen}
  <div
    class="h-screen bg-neutral-900 border-r border-neutral-800 flex flex-col relative"
    style="width: {$leftPanelWidth}px"
  >
    <!-- Drag Handle -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-blue-500/50 transition-colors z-50"
      onmousedown={startDrag}
      role="separator"
      aria-orientation="vertical"
      tabindex="0"
    ></div>

    <!-- Header -->
    <div
      class="h-12 px-4 border-b border-neutral-800 flex items-center justify-between relative"
    >
      <span class="text-sm font-semibold text-neutral-400">EXPLORER</span>

      <div class="flex gap-1">
        <button
          class="p-1 text-neutral-400 hover:text-neutral-100 rounded hover:bg-neutral-800"
          title="Search"
          onclick={() => ($isSearchOpen = true)}
        >
          <Search size={16} />
        </button>
        <button
          class="p-1 text-neutral-400 hover:text-neutral-100 rounded hover:bg-neutral-800"
          title="New Note{$selectedDirPath ? ' (in selected folder)' : ''}"
          onclick={handleNewNote}
        >
          <Plus size={16} />
        </button>
        <button
          class="p-1 text-neutral-400 hover:text-neutral-100 rounded hover:bg-neutral-800"
          title="New Folder{$selectedDirPath ? ' (in selected folder)' : ''}"
          onclick={handleNewFolder}
        >
          <FolderPlus size={16} />
        </button>
      </div>
    </div>

    <!-- File Tree -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="flex-grow overflow-y-auto p-2"
      oncontextmenu={handlePanelContextMenu}
    >
      <FileTreeNode path={null} name="Vault" isRoot={true} />
    </div>
  </div>
{/if}

<!-- Panel right-click context menu -->
{#if panelContextMenu}
  <ContextMenu
    x={panelContextMenu.x}
    y={panelContextMenu.y}
    items={[
      {
        label: "New Note",
        icon: "📄",
        action: () => handleNewNote(),
      },
      {
        label: "New Folder",
        icon: "📁",
        action: () => handleNewFolder(),
      },
    ]}
    onclose={() => (panelContextMenu = null)}
  />
{/if}

<!-- Drag overlay (follows cursor while dragging) -->
{#if $dragItem}
  <div
    class="fixed pointer-events-none z-[9999] px-3 py-1.5 rounded-md text-xs font-medium shadow-lg"
    style="left: {$dragPosition.x + 12}px; top: {$dragPosition.y -
      8}px; background: rgba(249,115,22,0.9); color: white;"
  >
    {$dragItem.name}
  </div>
{/if}
