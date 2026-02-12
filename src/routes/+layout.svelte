<script lang="ts">
  import NavRail from "$lib/components/layout/NavRail.svelte";
  import LeftPanel from "$lib/components/layout/LeftPanel.svelte";
  import RightPanel from "$lib/components/layout/RightPanel.svelte";
  import SearchModal from "$lib/components/search/SearchModal.svelte";
  import Toast from "$lib/components/Toast.svelte";
  import SplashScreen from "$lib/components/SplashScreen.svelte";
  import { setupNoteEventListeners } from "$lib/stores/notesStore";
  import { listen } from "@tauri-apps/api/event";
  import { onMount } from "svelte";
  import "../app.css";

  let { children } = $props();

  let backendReady = $state(false);
  let showSplash = $state(true);

  onMount(() => {
    const cleanupNoteListeners = setupNoteEventListeners();

    // Listen for backend ready signal
    const unlistenReady = listen("vault-ready", () => {
      console.log("Backend is ready!");
      backendReady = true;

      // Keep splash visible briefly for smooth transition
      setTimeout(() => {
        showSplash = false;
      }, 600);
    });

    // Safety timeout — if backend never signals, show the app anyway after 10s
    const safetyTimeout = setTimeout(() => {
      if (!backendReady) {
        console.warn("Backend ready timeout — showing app anyway");
        backendReady = true;
        setTimeout(() => {
          showSplash = false;
        }, 600);
      }
    }, 10000);

    return () => {
      cleanupNoteListeners();
      unlistenReady.then((fn) => fn());
      clearTimeout(safetyTimeout);
    };
  });
</script>

<!-- Splash screen overlays everything until backend signals ready -->
{#if showSplash}
  <SplashScreen visible={!backendReady} />
{/if}

<!-- App shell renders immediately (behind splash) for instant transition -->
<main class="flex h-screen bg-neutral-900 text-neutral-100 overflow-hidden">
  <NavRail />
  <LeftPanel />
  {@render children()}
  <RightPanel />
  <SearchModal />
  <Toast />
</main>
