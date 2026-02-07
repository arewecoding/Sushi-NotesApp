<script lang="ts">
    import {
        Bold,
        Italic,
        Link,
        List,
        PanelRightOpen,
        PanelRightClose,
        PanelLeftOpen,
        PanelLeftClose,
    } from "lucide-svelte";
    import { isRightPanelOpen, isLeftPanelOpen } from "$lib/stores/layout";

    let noteTitle = $state("Untitled Note");
</script>

<div class="h-screen flex-grow bg-neutral-900 flex flex-col font-mono">
    <!-- Editor Toolbar -->
    <div class="h-12 border-b border-neutral-800 flex items-center px-6 gap-2">
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
            onclick={() => ($isLeftPanelOpen = !$isLeftPanelOpen)}
            title={$isLeftPanelOpen ? "Close Explorer" : "Open Explorer"}
        >
            {#if $isLeftPanelOpen}
                <PanelLeftClose size={16} />
            {:else}
                <PanelLeftOpen size={16} />
            {/if}
        </button>
        <div class="w-px h-4 bg-neutral-800 mx-1"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Bold size={16} />
        </button>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Italic size={16} />
        </button>
        <div class="w-px h-4 bg-neutral-800 mx-1"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <List size={16} />
        </button>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
        >
            <Link size={16} />
        </button>

        <div class="flex-grow"></div>
        <span class="text-xs text-neutral-600">Saved</span>

        <div class="w-px h-4 bg-neutral-800 mx-2"></div>
        <button
            class="p-1.5 text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 rounded transition-colors"
            onclick={() => ($isRightPanelOpen = !$isRightPanelOpen)}
            title={$isRightPanelOpen
                ? "Close Details Panel"
                : "Open Details Panel"}
        >
            {#if $isRightPanelOpen}
                <PanelRightClose size={16} />
            {:else}
                <PanelRightOpen size={16} />
            {/if}
        </button>
    </div>

    <!-- Editor Content -->
    <div class="flex-grow overflow-y-auto p-12 max-w-4xl mx-auto w-full">
        <!-- Title -->
        <!-- Title -->
        <textarea
            class="text-4xl font-bold text-neutral-100 mb-8 outline-none bg-transparent w-full placeholder:text-neutral-600 resize-none overflow-hidden h-auto block"
            maxlength="256"
            rows="1"
            placeholder="Untitled Note"
            bind:value={noteTitle}
            oninput={(e) => {
                const target = e.currentTarget;
                target.style.height = "auto";
                target.style.height = target.scrollHeight + "px";
            }}
            onkeydown={(e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    // Focus the first editor block
                    const firstBlock = document.querySelector(".editor-block");
                    if (firstBlock instanceof HTMLElement) {
                        firstBlock.focus();
                    }
                }
            }}
        ></textarea>

        <!-- Blocks Placeholder -->
        <div class="space-y-4">
            <div
                class="editor-block text-neutral-300 outline-none p-2 hover:bg-neutral-800/20 rounded"
                contenteditable="true"
            >
                Start typing here...
            </div>
            <div
                class="editor-block text-neutral-300 outline-none p-2 hover:bg-neutral-800/20 rounded"
                contenteditable="true"
            >
                / to add blocks
            </div>
        </div>
    </div>
</div>
