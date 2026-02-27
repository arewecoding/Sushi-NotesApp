<script lang="ts">
    import {
        isRightPanelOpen,
        rightPanelWidth,
        rightPanelTab,
    } from "$lib/stores/layout";
    import ChatPanel from "$lib/components/chat/ChatPanel.svelte";
    import { MessageSquare, Info } from "lucide-svelte";

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
        const newWidth = window.innerWidth - event.clientX;
        $rightPanelWidth = Math.max(240, Math.min(520, newWidth));
    }
</script>

<svelte:window onmousemove={handleDrag} onmouseup={stopDrag} />

{#if $isRightPanelOpen}
    <div
        class="h-screen bg-neutral-900 border-l border-neutral-800 flex flex-col relative"
        style="width: {$rightPanelWidth}px; min-width: 240px;"
    >
        <!-- Drag Handle -->
        <button
            class="absolute top-0 left-0 w-1 h-full cursor-col-resize hover:bg-orange-500/40 transition-colors z-50 -ml-0.5 border-0 bg-transparent p-0"
            onmousedown={startDrag}
            aria-label="Resize panel"
            title="Drag to resize"
        ></button>

        <!-- Tab Bar -->
        <div
            class="h-12 border-b border-neutral-800 flex items-stretch px-2 gap-0 flex-shrink-0"
        >
            <button
                class="flex items-center gap-1.5 px-3 text-xs font-medium transition-colors border-b-2 -mb-px
                       {$rightPanelTab === 'details'
                    ? 'border-orange-500 text-neutral-100'
                    : 'border-transparent text-neutral-500 hover:text-neutral-300'}"
                onclick={() => ($rightPanelTab = "details")}
            >
                <Info size={13} />
                Details
            </button>
            <button
                class="flex items-center gap-1.5 px-3 text-xs font-medium transition-colors border-b-2 -mb-px
                       {$rightPanelTab === 'chat'
                    ? 'border-orange-500 text-neutral-100'
                    : 'border-transparent text-neutral-500 hover:text-neutral-300'}"
                onclick={() => ($rightPanelTab = "chat")}
            >
                <MessageSquare size={13} />
                Ask AI
            </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-hidden flex flex-col">
            {#if $rightPanelTab === "details"}
                <!-- Details Panel (existing placeholder content) -->
                <div class="p-4 space-y-6 overflow-y-auto">
                    <div>
                        <div class="text-xs text-neutral-500 uppercase mb-2">
                            Created
                        </div>
                        <div class="text-sm text-neutral-300">—</div>
                    </div>

                    <div>
                        <div class="text-xs text-neutral-500 uppercase mb-2">
                            Tags
                        </div>
                        <div class="flex flex-wrap gap-2">
                            <span
                                class="px-2 py-1 bg-neutral-800 text-neutral-400 text-xs rounded-full italic"
                            >
                                No tags yet
                            </span>
                        </div>
                    </div>

                    <div>
                        <div class="text-xs text-neutral-500 uppercase mb-2">
                            Backlinks
                        </div>
                        <div class="text-sm text-neutral-600 italic">None</div>
                    </div>

                    <div class="pt-2 border-t border-neutral-800">
                        <div class="text-xs text-neutral-600">
                            💡 Tip: Use <code
                                class="text-orange-500/80 font-mono bg-neutral-800 px-1 rounded text-[11px]"
                                >[[Link Text|note_id]]</code
                            > syntax to link notes together.
                        </div>
                    </div>
                </div>
            {:else}
                <!-- RAG Chatbot -->
                <ChatPanel />
            {/if}
        </div>
    </div>
{/if}
