<script lang="ts">
  import { Plus, FolderPlus, Search } from "lucide-svelte";
  import {
    leftPanelWidth,
    isLeftPanelOpen,
    isSearchOpen,
  } from "$lib/stores/layout";
  import { createAndOpenNote } from "$lib/stores/notesStore";
  import { treeVersion, refreshTree } from "$lib/stores/fileTreeStore";
  import FileTreeNode from "./FileTreeNode.svelte";
  import { listen } from "@tauri-apps/api/event";
  import { onMount } from "svelte";

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
    if (!isDragging) return;

    // Clamp between 200 and 500
    const newWidth = Math.max(200, Math.min(500, event.clientX));
    $leftPanelWidth = newWidth;
  }

  // Listen for tree-changed events from backend
  // This listener is in LeftPanel, NOT in FileTreeNode, so it won't be
  // destroyed when the tree is re-rendered via {#key}
  onMount(() => {
    const unlisten = listen<{
      changed_path: string;
      event_type: string;
    }>("tree-changed", (event) => {
      console.log("Tree changed event received:", event.payload);
      // Increment tree version to force complete re-render of all nodes
      refreshTree();
    });

    return () => {
      // Cleanup listener on unmount
      unlisten.then((fn) => fn());
    };
  });
</script>

<svelte:window onmousemove={handleDrag} onmouseup={stopDrag} />

{#if $isLeftPanelOpen}
  <div
    class="h-screen bg-neutral-900 border-r border-neutral-800 flex flex-col relative"
    style="width: {$leftPanelWidth}px"
  >
    <!-- Drag Handle -->
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
          title="New Note"
          onclick={() => createAndOpenNote()}
        >
          <Plus size={16} />
        </button>
        <button
          class="p-1 text-neutral-400 hover:text-neutral-100 rounded hover:bg-neutral-800"
          title="New Folder"
        >
          <FolderPlus size={16} />
        </button>
      </div>
    </div>

    <!-- File Tree (keyed to force re-render on tree changes) -->
    <div class="flex-grow overflow-y-auto p-2">
      {#key $treeVersion}
        <FileTreeNode path={null} name="Vault" isRoot={true} />
      {/key}
    </div>
  </div>
{/if}
