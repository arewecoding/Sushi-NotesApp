<script lang="ts">
    import { isRightPanelOpen, rightPanelWidth } from "$lib/stores/layout";

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

        // Calculate width from the right side of the screen
        const newWidth = window.innerWidth - event.clientX;
        // Clamp between 200 and 500
        $rightPanelWidth = Math.max(200, Math.min(500, newWidth));
    }
</script>

<svelte:window onmousemove={handleDrag} onmouseup={stopDrag} />

{#if $isRightPanelOpen}
    <div
        class="h-screen bg-neutral-900 border-l border-neutral-800 flex flex-col relative"
        style="width: {$rightPanelWidth}px"
    >
        <!-- Drag Handle -->
        <div
            class="absolute top-0 left-0 w-1 h-full cursor-col-resize hover:bg-blue-500/50 transition-colors z-50 -ml-0.5"
            onmousedown={startDrag}
            role="separator"
            aria-orientation="vertical"
            tabindex="0"
        ></div>
        <div
            class="h-12 px-4 border-b border-neutral-800 flex justify-between items-center"
        >
            <span class="text-sm font-bold text-neutral-400">DETAILS</span>
        </div>

        <div class="p-4 space-y-6">
            <div>
                <div class="text-xs text-neutral-500 uppercase mb-2">
                    Created
                </div>
                <div class="text-sm text-neutral-300">Jan 14, 2024</div>
            </div>

            <div>
                <div class="text-xs text-neutral-500 uppercase mb-2">Tags</div>
                <div class="flex flex-wrap gap-2">
                    <span
                        class="px-2 py-1 bg-neutral-800 text-neutral-300 text-xs rounded-full"
                        >#project</span
                    >
                    <span
                        class="px-2 py-1 bg-neutral-800 text-neutral-300 text-xs rounded-full"
                        >#wip</span
                    >
                </div>
            </div>

            <div>
                <div class="text-xs text-neutral-500 uppercase mb-2">
                    Backlinks
                </div>
                <div
                    class="text-sm text-blue-400 hover:underline cursor-pointer"
                >
                    Project Plan
                </div>
            </div>
        </div>
    </div>
{/if}
