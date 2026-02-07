<script lang="ts">
    import { Search, X, Clock, FileText } from "lucide-svelte";
    import { fade, scale } from "svelte/transition";
    import { isSearchOpen } from "$lib/stores/layout";

    let searchQuery = $state("");
    let searchInput: HTMLInputElement;

    function close() {
        $isSearchOpen = false;
        searchQuery = "";
    }

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === "Escape") close();
    }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if $isSearchOpen}
    <div
        class="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] bg-black/50 backdrop-blur-sm"
        transition:fade={{ duration: 150 }}
        onclick={close}
    >
        <div
            class="w-full max-w-2xl bg-neutral-900/90 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden flex flex-col"
            transition:scale={{ start: 0.95, duration: 150 }}
            onclick={(e) => e.stopPropagation()}
        >
            <!-- Search Header -->
            <div
                class="flex items-center p-4 border-b border-neutral-800 gap-4"
            >
                <Search class="text-neutral-500" size={24} />
                <input
                    bind:this={searchInput}
                    bind:value={searchQuery}
                    type="text"
                    placeholder="Search anything..."
                    class="flex-1 bg-transparent text-xl text-neutral-200 placeholder:text-neutral-600 outline-none"
                    autofocus
                />
                <button
                    class="p-1 text-neutral-500 hover:text-neutral-300 rounded"
                    onclick={() => {
                        if (searchQuery) {
                            searchQuery = "";
                            searchInput.focus();
                        } else {
                            close();
                        }
                    }}
                >
                    <X size={20} />
                </button>
            </div>

            <!-- Content Area -->
            <div class="max-h-[60vh] overflow-y-auto p-2">
                {#if searchQuery === ""}
                    <!-- Suggestions / Recent -->
                    <div
                        class="p-2 text-xs font-semibold text-neutral-500 uppercase mb-2"
                    >
                        Recent Searches
                    </div>
                    <div class="space-y-1">
                        {#each ["Project Plan", "Meeting Notes", "Design System"] as item}
                            <button
                                class="w-full flex items-center gap-3 p-3 hover:bg-neutral-800/50 rounded-lg text-left group transition-colors"
                            >
                                <Clock
                                    class="text-neutral-500 group-hover:text-neutral-300"
                                    size={18}
                                />
                                <span
                                    class="text-neutral-300 group-hover:text-white"
                                    >{item}</span
                                >
                            </button>
                        {/each}
                    </div>
                {:else}
                    <!-- Results -->
                    <div
                        class="p-2 text-xs font-semibold text-neutral-500 uppercase mb-2"
                    >
                        Results
                    </div>
                    <div class="space-y-1">
                        {#each ["Architecture Doc", "API Reference", "Q1 Goals"] as item}
                            <button
                                class="w-full flex items-center gap-3 p-3 hover:bg-neutral-800/50 rounded-lg text-left group transition-colors"
                            >
                                <FileText
                                    class="text-neutral-500 group-hover:text-blue-400"
                                    size={18}
                                />
                                <div>
                                    <div
                                        class="text-neutral-200 group-hover:text-white font-medium"
                                    >
                                        {item}
                                    </div>
                                    <div class="text-xs text-neutral-500">
                                        Found in Documents
                                    </div>
                                </div>
                            </button>
                        {/each}
                    </div>
                {/if}
            </div>

            <!-- Footer -->
            <div
                class="p-3 bg-neutral-950/50 border-t border-neutral-800 flex justify-end gap-4 text-xs text-neutral-500"
            >
                <div class="flex items-center gap-1">
                    <kbd
                        class="px-1.5 py-0.5 bg-neutral-800 rounded border border-neutral-700 font-sans"
                        >esc</kbd
                    >
                    <span>to close</span>
                </div>
                <div class="flex items-center gap-1">
                    <kbd
                        class="px-1.5 py-0.5 bg-neutral-800 rounded border border-neutral-700 font-sans"
                        >↵</kbd
                    >
                    <span>to select</span>
                </div>
            </div>
        </div>
    </div>
{/if}
