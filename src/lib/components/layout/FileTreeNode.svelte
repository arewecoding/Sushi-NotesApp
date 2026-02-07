<script lang="ts">
    import {
        ChevronRight,
        ChevronDown,
        Folder,
        FileText,
        Loader2,
    } from "lucide-svelte";
    import { getDirectoryContents } from "../../../client/apiClient";
    import type {
        DirectoryItem,
        NoteListItem,
    } from "../../../client/_apiTypes";
    import { loadNote, activeNoteId } from "$lib/stores/notesStore";
    import { addToast } from "$lib/stores/toastStore";

    interface Props {
        path: string | null;
        name: string;
        isRoot?: boolean;
    }

    let { path, name, isRoot = false }: Props = $props();

    let isExpanded = $state(isRoot); // Root starts expanded
    let isLoading = $state(false);
    let isLoaded = $state(false);
    let subdirs = $state<DirectoryItem[]>([]);
    let notes = $state<NoteListItem[]>([]);

    async function fetchContents() {
        isLoading = true;
        try {
            const contents = await getDirectoryContents(path);
            subdirs = contents.subdirs;
            notes = contents.notes;
            isLoaded = true;
        } catch (error) {
            console.error("Failed to load directory contents:", error);
            addToast("error", `Failed to load ${name}`);
        } finally {
            isLoading = false;
        }
    }

    async function toggleExpand() {
        if (!isExpanded && !isLoaded) {
            // First time expanding - fetch contents
            await fetchContents();
        }
        isExpanded = !isExpanded;
    }

    function handleNoteClick(noteId: string) {
        loadNote(noteId);
    }

    // Auto-load root on mount
    $effect(() => {
        if (isRoot && !isLoaded) {
            toggleExpand();
        }
    });
</script>

<div class="select-none">
    <!-- Directory Header -->
    {#if !isRoot}
        <button
            class="w-full flex items-center gap-1 text-sm text-neutral-400 px-2 py-1
             hover:bg-neutral-800 hover:text-neutral-200 cursor-pointer rounded text-left"
            onclick={toggleExpand}
        >
            {#if isLoading}
                <Loader2 size={14} class="animate-spin flex-shrink-0" />
            {:else if isExpanded}
                <ChevronDown size={14} class="flex-shrink-0" />
            {:else}
                <ChevronRight size={14} class="flex-shrink-0" />
            {/if}
            <Folder size={14} class="flex-shrink-0 text-yellow-500/70" />
            <span class="truncate">{name}</span>
        </button>
    {/if}

    <!-- Contents (subdirs + notes) -->
    {#if isExpanded || isRoot}
        <div class={isRoot ? "" : "pl-4"}>
            {#if isLoading && isRoot}
                <div
                    class="flex items-center justify-center py-4 text-neutral-500"
                >
                    <Loader2 size={18} class="animate-spin" />
                </div>
            {:else}
                <!-- Subdirectories -->
                {#each subdirs as dir (dir.dirPath)}
                    <svelte:self path={dir.dirPath} name={dir.dirName} />
                {/each}

                <!-- Notes -->
                {#each notes as note (note.noteId)}
                    <button
                        class="w-full flex items-center gap-2 text-sm text-neutral-400 px-2 py-1
                   hover:bg-neutral-800 hover:text-neutral-200 cursor-pointer rounded text-left
                   transition-colors {$activeNoteId === note.noteId
                            ? 'bg-neutral-800 text-neutral-100'
                            : ''}"
                        onclick={() => handleNoteClick(note.noteId)}
                    >
                        <FileText size={14} class="flex-shrink-0" />
                        <span class="truncate">{note.noteTitle}</span>
                    </button>
                {/each}

                <!-- Empty state -->
                {#if isLoaded && subdirs.length === 0 && notes.length === 0}
                    <div class="text-xs text-neutral-600 px-2 py-1 italic">
                        Empty folder
                    </div>
                {/if}
            {/if}
        </div>
    {/if}
</div>
