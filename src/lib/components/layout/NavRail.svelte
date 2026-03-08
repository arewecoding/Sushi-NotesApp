<script lang="ts">
  /**
   * NavRail.svelte
   * ==============
   * Narrow left-edge navigation rail with icons for Notes, Daily Board,
   * Calendar, Graph View, and Settings. Currently only Notes is
   * functional; the others are placeholder buttons for future features.
   */
  import {
    FileText,
    Calendar,
    Network,
    Settings,
    LayoutGrid,
  } from "lucide-svelte";
  import { activeNoteId, activeNoteContent } from "$lib/stores/notesStore";

  function goHome() {
    $activeNoteId = null;
    $activeNoteContent = null;
  }
</script>

<div
  class="h-screen w-16 bg-neutral-900 border-r border-neutral-800 flex flex-col items-center py-4 gap-6"
>
  <!-- Logo / Home Button -->
  <div class="mb-4">
    <button
      class="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-neutral-800 transition-all duration-200 group cursor-pointer"
      onclick={goHome}
      title="Home"
    >
      <img
        src="/logo2.png"
        alt="Sushi"
        class="w-7 h-7 object-contain group-hover:scale-110 transition-transform duration-200"
      />
    </button>
  </div>

  <!-- Nav Items -->
  <button
    class="p-2 text-neutral-100 bg-neutral-800 rounded-md hover:bg-neutral-700 transition-colors"
    title="Notes"
  >
    <FileText size={20} />
  </button>

  <button
    class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors"
    title="Daily Board"
  >
    <LayoutGrid size={20} />
  </button>

  <button
    class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors"
    title="Calendar"
  >
    <Calendar size={20} />
  </button>

  <button
    class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors"
    title="Graph View"
  >
    <Network size={20} />
  </button>

  <div class="flex-grow"></div>

  <button
    class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors"
    title="Settings"
  >
    <Settings size={20} />
  </button>
</div>
