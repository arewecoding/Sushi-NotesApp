<script lang="ts">
  import { toasts, removeToast, type ToastType } from '$lib/stores/toastStore';
  import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-svelte';

  function getIcon(type: ToastType) {
    switch (type) {
      case 'success': return CheckCircle;
      case 'error': return AlertCircle;
      case 'warning': return AlertTriangle;
      default: return Info;
    }
  }

  function getColors(type: ToastType): string {
    switch (type) {
      case 'success': return 'bg-green-900/80 border-green-700 text-green-100';
      case 'error': return 'bg-red-900/80 border-red-700 text-red-100';
      case 'warning': return 'bg-yellow-900/80 border-yellow-700 text-yellow-100';
      default: return 'bg-blue-900/80 border-blue-700 text-blue-100';
    }
  }
</script>

<div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
  {#each $toasts as toast (toast.id)}
    <div
      class="flex items-center gap-3 p-3 rounded-lg border shadow-lg backdrop-blur-sm animate-slide-in {getColors(toast.type)}"
      role="alert"
    >
      <svelte:component this={getIcon(toast.type)} size={18} />
      <span class="flex-1 text-sm">{toast.message}</span>
      <button
        class="p-1 hover:bg-white/10 rounded transition-colors"
        onclick={() => removeToast(toast.id)}
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  {/each}
</div>

<style>
  @keyframes slide-in {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  
  .animate-slide-in {
    animation: slide-in 0.2s ease-out;
  }
</style>
