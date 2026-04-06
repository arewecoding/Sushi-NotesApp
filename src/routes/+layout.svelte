<script lang="ts">
  import NavRail from "$lib/components/layout/NavRail.svelte";
  import LeftPanel from "$lib/components/layout/LeftPanel.svelte";
  import RightPanel from "$lib/components/layout/RightPanel.svelte";
  import SearchModal from "$lib/components/search/SearchModal.svelte";
  import SettingsModal from "$lib/components/settings/SettingsModal.svelte";
  import Toast from "$lib/components/Toast.svelte";
  import SplashScreen from "$lib/components/SplashScreen.svelte";
  import CanvasView from "$lib/components/layout/CanvasView.svelte";
  import { setupNoteEventListeners } from "$lib/stores/notesStore";
  import { activeMainTab } from "$lib/stores/layoutStore";
  import { initGlobalErrorHandler } from "$lib/canvas/errorForwarding";
  import { listen } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { onMount } from "svelte";
  import { initDiagnosticsPiping } from "$lib/client/diagnostics";
  import "../app.css";

  // Bootstrap custom diagnostics
  initDiagnosticsPiping();


  let { children } = $props();

  let backendReady = $state(false);
  let showSplash = $state(true);

  onMount(() => {
    const cleanupNoteListeners = setupNoteEventListeners();
    initGlobalErrorHandler();

    // ── Flush canvas blocks on app close ──────────────────────────────────
    const BEFORE_CLOSE_FLUSH_MS = 500;
    const unlistenClose = getCurrentWindow().onCloseRequested(async (event) => {
      event.preventDefault();
      // Signal all active canvas blocks to flush cached data
      window.dispatchEvent(new CustomEvent("sushi:beforeclose"));
      // Give IPC calls a moment to reach the backend
      await new Promise((r) => setTimeout(r, BEFORE_CLOSE_FLUSH_MS));
      await getCurrentWindow().destroy();
    });

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
      unlistenClose.then((fn) => fn());
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
  {#if $activeMainTab === 'notes'}
    <LeftPanel />
    {@render children()}
    <RightPanel />
  {:else if $activeMainTab === 'canvas'}
    <CanvasView />
  {/if}
  <SearchModal />
  <SettingsModal />
  <Toast />
</main>

