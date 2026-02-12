<script lang="ts">
    import { X } from "lucide-svelte";

    let {
        open = false,
        title = "Confirm",
        message = "Are you sure?",
        confirmLabel = "Delete",
        cancelLabel = "Cancel",
        localStorageKey = "",
        onconfirm = () => {},
        oncancel = () => {},
    } = $props();

    let dontShowAgain = $state(false);

    function handleConfirm() {
        if (dontShowAgain && localStorageKey) {
            localStorage.setItem(localStorageKey, "true");
        }
        onconfirm();
    }

    function handleCancel() {
        dontShowAgain = false;
        oncancel();
    }
</script>

{#if open}
    <!-- Backdrop -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
        class="fixed inset-0 z-[9000] flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onmousedown={(e) => {
            if (e.target === e.currentTarget) handleCancel();
        }}
        role="dialog"
        aria-modal="true"
    >
        <!-- Dialog -->
        <div
            class="bg-neutral-800 border border-neutral-700 rounded-xl shadow-2xl w-[380px] overflow-hidden animate-dialog-in"
        >
            <!-- Header -->
            <div
                class="flex items-center justify-between px-5 py-4 border-b border-neutral-700"
            >
                <h3 class="text-sm font-semibold text-neutral-100">{title}</h3>
                <button
                    class="p-1 text-neutral-400 hover:text-neutral-100 rounded hover:bg-neutral-700 transition-colors"
                    onclick={handleCancel}
                >
                    <X size={14} />
                </button>
            </div>

            <!-- Body -->
            <div class="px-5 py-4">
                <p class="text-sm text-neutral-300 leading-relaxed">
                    {message}
                </p>

                {#if localStorageKey}
                    <label
                        class="flex items-center gap-2 mt-4 cursor-pointer group"
                    >
                        <input
                            type="checkbox"
                            bind:checked={dontShowAgain}
                            class="accent-orange-500 rounded"
                        />
                        <span
                            class="text-xs text-neutral-500 group-hover:text-neutral-400 transition-colors"
                        >
                            Don't ask me again
                        </span>
                    </label>
                {/if}
            </div>

            <!-- Footer -->
            <div
                class="flex justify-end gap-2 px-5 py-3 border-t border-neutral-700 bg-neutral-800/50"
            >
                <button
                    class="px-4 py-1.5 text-sm text-neutral-300 hover:text-neutral-100 hover:bg-neutral-700 rounded-lg transition-colors"
                    onclick={handleCancel}
                >
                    {cancelLabel}
                </button>
                <button
                    class="px-4 py-1.5 text-sm text-white bg-red-600 hover:bg-red-500 rounded-lg transition-colors font-medium"
                    onclick={handleConfirm}
                >
                    {confirmLabel}
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    @keyframes dialog-in {
        from {
            opacity: 0;
            transform: scale(0.95) translateY(8px);
        }
        to {
            opacity: 1;
            transform: scale(1) translateY(0);
        }
    }

    .animate-dialog-in {
        animation: dialog-in 0.15s ease-out;
    }
</style>
