<script lang="ts">
    /**
     * ChatPanel.svelte
     * ================
     * RAG chatbot panel for the right sidebar.
     */

    import { onMount, tick } from "svelte";
    import {
        Bot,
        Send,
        Trash2,
        ChevronDown,
        ChevronUp,
        Zap,
        Database,
    } from "lucide-svelte";
    import {
        chatHistory,
        isRagLoading,
        isIndexBuilding,
        ragStatusData,
        sendRagQuery,
        buildRagIndex,
        refreshRagStatus,
        clearChat,
    } from "$lib/stores/ragStore";
    import type { ChatMessage } from "$lib/stores/ragStore";
    import { activeNoteContent } from "$lib/stores/notesStore";

    let input = $state("");
    let messagesEl = $state<HTMLElement | null>(null);
    let expandedMetaIds = $state<Set<string>>(new Set());

    /** Convert **bold** markdown and \n to HTML for rendering. */
    function formatMessage(text: string): string {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
            .replace(/\n/g, "<br>");
    }

    onMount(async () => {
        await refreshRagStatus();
        if ($chatHistory.length === 0) {
            chatHistory.update((h) => [
                ...h,
                {
                    id: "welcome",
                    role: "assistant",
                    content: $ragStatusData?.ragEnabled
                        ? "👋 Hi! I can answer questions about your notes using semantic search and graph reasoning.\n\nIf you haven't indexed your vault yet, click **Build Index** first."
                        : "👋 Hi! The RAG backend is not ready (check `google_api_key` in `rag_config.json`).\n\nOnce configured, click **Build Index** then ask me anything.",
                    timestamp: Date.now(),
                } satisfies ChatMessage,
            ]);
        }
    });

    $effect(() => {
        const _ = $chatHistory;
        tick().then(() => {
            if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
        });
    });

    async function handleSend() {
        const query = input.trim();
        if (!query || $isRagLoading) return;
        input = "";
        await sendRagQuery(query);
    }

    function handleKeyDown(e: KeyboardEvent) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    }

    function toggleMeta(id: string) {
        expandedMetaIds = new Set(
            expandedMetaIds.has(id)
                ? [...expandedMetaIds].filter((x) => x !== id)
                : [...expandedMetaIds, id],
        );
    }

    function formatLatency(latency: Record<string, number>): string {
        const total =
            latency.total ?? Object.values(latency).reduce((a, b) => a + b, 0);
        return total ? `${(total * 1000).toFixed(0)}ms` : "–";
    }

    function strategyLabel(strategy: string): string {
        const map: Record<string, string> = {
            direct_recall: "Direct Recall",
            contextual_traversal: "Graph Traversal",
            disabled: "RAG Disabled",
            error: "Error",
        };
        return map[strategy] ?? strategy;
    }

    function askAboutCurrentNote() {
        const title = $activeNoteContent?.title;
        if (title) input = `What do I know about "${title}"?`;
    }
</script>

<div class="flex flex-col h-full">
    <!-- Header Actions -->
    <div
        class="flex items-center gap-1 px-3 py-2 border-b border-neutral-800 flex-shrink-0"
    >
        <button
            class="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded
                   bg-orange-500/10 text-orange-400 hover:bg-orange-500/20
                   transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            onclick={buildRagIndex}
            disabled={$isIndexBuilding || $isRagLoading}
            title="Rebuild the RAG index from all vault notes"
        >
            <Database size={12} />
            {$isIndexBuilding ? "Indexing…" : "Build Index"}
        </button>

        {#if $activeNoteContent}
            <button
                class="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded
                       bg-neutral-800 text-neutral-400 hover:text-neutral-200
                       hover:bg-neutral-700 transition-colors"
                onclick={askAboutCurrentNote}
                title="Ask about the current note"
            >
                <Zap size={12} />
                This note
            </button>
        {/if}

        <div class="flex-grow"></div>

        <div
            class="w-2 h-2 rounded-full {$ragStatusData?.ragEnabled
                ? 'bg-green-500'
                : 'bg-neutral-600'}"
            title={$ragStatusData?.ragEnabled
                ? `${$ragStatusData.faissVectors} vectors indexed`
                : "RAG not available"}
        ></div>

        <button
            class="p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
            onclick={clearChat}
            title="Clear chat"
        >
            <Trash2 size={13} />
        </button>
    </div>

    <!-- Messages -->
    <div
        bind:this={messagesEl}
        class="flex-grow overflow-y-auto px-3 py-3 space-y-3 scroll-smooth"
    >
        {#each $chatHistory as msg (msg.id)}
            <div
                class="flex flex-col {msg.role === 'user'
                    ? 'items-end'
                    : 'items-start'}"
            >
                {#if msg.role === "user"}
                    <div
                        class="max-w-[85%] px-3 py-2 rounded-2xl rounded-tr-sm
                                bg-orange-500/20 text-orange-100 text-sm leading-relaxed"
                    >
                        {msg.content}
                    </div>
                {:else}
                    <div class="flex items-start gap-1.5 max-w-full">
                        <div
                            class="w-5 h-5 rounded-full bg-neutral-700 flex items-center
                                    justify-center flex-shrink-0 mt-0.5"
                        >
                            <Bot size={11} class="text-orange-400" />
                        </div>
                        <div class="flex-1 min-w-0">
                            <div
                                class="px-3 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed
                                        {msg.isError
                                    ? 'bg-red-500/10 text-red-300 border border-red-500/20'
                                    : 'bg-neutral-800 text-neutral-200'}"
                            >
                                {@html formatMessage(msg.content)}
                            </div>

                            {#if msg.metadata}
                                <button
                                    class="flex items-center gap-1 mt-1 px-1.5 py-0.5 text-[10px]
                                           text-neutral-500 hover:text-neutral-400 transition-colors"
                                    onclick={() => toggleMeta(msg.id)}
                                >
                                    {#if expandedMetaIds.has(msg.id)}
                                        <ChevronUp size={10} />
                                    {:else}
                                        <ChevronDown size={10} />
                                    {/if}
                                    {strategyLabel(msg.metadata.strategy)} · {formatLatency(
                                        msg.metadata.latency,
                                    )} · {msg.metadata.blocksInContext} blocks
                                </button>

                                {#if expandedMetaIds.has(msg.id)}
                                    <div
                                        class="mt-1 px-2 py-1.5 bg-neutral-800/50 rounded-lg
                                                border border-neutral-700/50 text-[11px]
                                                text-neutral-500 space-y-0.5"
                                    >
                                        <div>
                                            <span class="text-neutral-400"
                                                >Strategy:</span
                                            >
                                            {strategyLabel(
                                                msg.metadata.strategy,
                                            )}
                                        </div>
                                        <div>
                                            <span class="text-neutral-400"
                                                >Retrieved:</span
                                            >
                                            {msg.metadata.blocksRetrieved} blocks
                                        </div>
                                        <div>
                                            <span class="text-neutral-400"
                                                >In context:</span
                                            >
                                            {msg.metadata.blocksInContext} blocks
                                        </div>
                                        <div>
                                            <span class="text-neutral-400"
                                                >Latency:</span
                                            >
                                            {formatLatency(
                                                msg.metadata.latency,
                                            )}
                                        </div>
                                    </div>
                                {/if}
                            {/if}
                        </div>
                    </div>
                {/if}
            </div>
        {/each}

        {#if $isRagLoading}
            <div class="flex items-center gap-1.5">
                <div
                    class="w-5 h-5 rounded-full bg-neutral-700 flex items-center justify-center"
                >
                    <Bot size={11} class="text-orange-400" />
                </div>
                <div
                    class="bg-neutral-800 px-3 py-2.5 rounded-2xl rounded-tl-sm flex gap-1 items-center"
                >
                    <span
                        class="w-1.5 h-1.5 bg-neutral-500 rounded-full animate-bounce [animation-delay:-0.3s]"
                    ></span>
                    <span
                        class="w-1.5 h-1.5 bg-neutral-500 rounded-full animate-bounce [animation-delay:-0.15s]"
                    ></span>
                    <span
                        class="w-1.5 h-1.5 bg-neutral-500 rounded-full animate-bounce"
                    ></span>
                </div>
            </div>
        {/if}
    </div>

    <!-- Input area -->
    <div class="border-t border-neutral-800 p-3 flex-shrink-0">
        <div class="flex items-end gap-2 bg-neutral-800 rounded-xl px-3 py-2">
            <textarea
                class="flex-grow bg-transparent text-sm text-neutral-200
                       placeholder:text-neutral-600 outline-none resize-none
                       max-h-32 leading-relaxed"
                placeholder="Ask about your notes…"
                rows="1"
                bind:value={input}
                onkeydown={handleKeyDown}
                oninput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = "auto";
                    t.style.height = Math.min(t.scrollHeight, 128) + "px";
                }}
                disabled={$isRagLoading}
            ></textarea>
            <button
                class="p-1.5 rounded-lg transition-colors flex-shrink-0
                       {input.trim() && !$isRagLoading
                    ? 'text-orange-400 hover:text-orange-300 hover:bg-orange-500/10'
                    : 'text-neutral-600 cursor-not-allowed'}"
                onclick={handleSend}
                disabled={!input.trim() || $isRagLoading}
                title="Send (Enter)"
            >
                <Send size={16} />
            </button>
        </div>
        <p class="text-[10px] text-neutral-700 text-center mt-1.5">
            Powered by Gemini · Answers drawn from your notes
        </p>
    </div>
</div>

<style>
    :global(.inline-code) {
        font-family: monospace;
        font-size: 0.85em;
        background: rgba(255, 255, 255, 0.08);
        padding: 1px 4px;
        border-radius: 3px;
        color: #fb923c;
    }
</style>
