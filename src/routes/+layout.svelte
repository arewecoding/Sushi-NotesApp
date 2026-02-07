<script lang="ts">
  import NavRail from "$lib/components/layout/NavRail.svelte";
  import LeftPanel from "$lib/components/layout/LeftPanel.svelte";
  import RightPanel from "$lib/components/layout/RightPanel.svelte";
  import SearchModal from "$lib/components/search/SearchModal.svelte";
  import Toast from "$lib/components/Toast.svelte";
  import { setupNoteEventListeners } from "$lib/stores/notesStore";
  import { onMount } from "svelte";
  import "../app.css";

  let { children } = $props();

  // Setup backend event listeners on mount
  onMount(() => {
    const cleanupNoteListeners = setupNoteEventListeners();

    return () => {
      cleanupNoteListeners();
    };
  });
</script>

<main class="flex h-screen bg-neutral-900 text-neutral-100 overflow-hidden">
  <NavRail />
  <LeftPanel />
  {@render children()}
  <RightPanel />
  <SearchModal />
  <Toast />
</main>
