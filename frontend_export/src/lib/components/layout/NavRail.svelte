<script lang="ts">
  import { FileText, Calendar, Network, Settings, LayoutGrid } from 'lucide-svelte';
</script>

<div class="h-screen w-16 bg-neutral-900 border-r border-neutral-800 flex flex-col items-center py-4 gap-6">
  <!-- Logo/Brand generic icon -->
  <div class="mb-4">
    <div class="w-8 h-8 bg-neutral-800 rounded-lg flex items-center justify-center text-neutral-400 font-bold">
      V
    </div>
  </div>

  <!-- Nav Items -->
  <button class="p-2 text-neutral-100 bg-neutral-800 rounded-md hover:bg-neutral-700 transition-colors" title="Notes">
    <FileText size={20} />
  </button>
  
  <button class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors" title="Daily Board">
    <LayoutGrid size={20} />
  </button>

  <button class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors" title="Calendar">
    <Calendar size={20} />
  </button>

  <button class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors" title="Graph View">
    <Network size={20} />
  </button>

  <div class="flex-grow"></div>

  <button class="p-2 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded-md transition-colors" title="Settings">
    <Settings size={20} />
  </button>
</div>
