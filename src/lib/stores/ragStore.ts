/**
 * ragStore.ts
 * ===========
 * Svelte store for the RAG chatbot panel.
 *
 * Manages chat history, loading state, and RAG status.
 * Calls backend via ragApiClient.ts.
 */

import { writable, get } from "svelte/store";
import { ragQuery, ragBuildIndex, ragStatus } from "$lib/client/ragApiClient";
import type { RagQueryResponse, RagStatusResponse } from "$lib/client/ragApiClient";
import { addToast } from "./toastStore";

// ── Types ─────────────────────────────────────────────────────────────────

export interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    metadata?: {
        strategy: string;
        blocksRetrieved: number;
        blocksInContext: number;
        latency: Record<string, number>;
        ragEnabled: boolean;
    };
    timestamp: number;
    isError?: boolean;
}

// ── Stores ────────────────────────────────────────────────────────────────

export const chatHistory = writable<ChatMessage[]>([]);
export const isRagLoading = writable(false);
export const isIndexBuilding = writable(false);
export const ragStatusData = writable<RagStatusResponse | null>(null);

// ── Actions ───────────────────────────────────────────────────────────────

/**
 * Send a query to the RAG pipeline and append the response to chat history.
 */
export async function sendRagQuery(userMessage: string): Promise<void> {
    if (!userMessage.trim()) return;

    const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: userMessage.trim(),
        timestamp: Date.now(),
    };

    chatHistory.update((h) => [...h, userMsg]);
    isRagLoading.set(true);

    try {
        const result: RagQueryResponse = await ragQuery(userMessage.trim());

        const assistantMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.answer,
            metadata: {
                strategy: result.strategy,
                blocksRetrieved: result.blocksRetrieved,
                blocksInContext: result.blocksInContext,
                latency: result.latency,
                ragEnabled: result.ragEnabled,
            },
            timestamp: Date.now(),
            isError: !result.ragEnabled || result.strategy === "error",
        };

        chatHistory.update((h) => [...h, assistantMsg]);
    } catch (err) {
        const errMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `Failed to reach the RAG backend: ${err}`,
            timestamp: Date.now(),
            isError: true,
        };
        chatHistory.update((h) => [...h, errMsg]);
        addToast("error", "RAG query failed");
    } finally {
        isRagLoading.set(false);
    }
}

/**
 * Rebuild the entire RAG index from the vault.
 */
export async function buildRagIndex(): Promise<void> {
    isIndexBuilding.set(true);

    // Optimistic UX: tell the user indexing started
    const buildingMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
            "🔄 Building the knowledge index over your vault… This may take a minute. I'll let you know when it's ready.",
        timestamp: Date.now(),
    };
    chatHistory.update((h) => [...h, buildingMsg]);

    try {
        const result = await ragBuildIndex();
        const doneMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.ragEnabled
                ? `✅ Index built! Indexed **${result.notesIndexed}** notes, **${result.blocksIndexed}** blocks. Knowledge graph: ${result.graphNodes} nodes, ${result.graphEdges} edges. You can now ask questions about your notes.`
                : `⚠️ Indexing failed: ${result.message}`,
            timestamp: Date.now(),
            isError: !result.ragEnabled,
        };
        chatHistory.update((h) => [...h, doneMsg]);

        // Refresh status
        await refreshRagStatus();
    } catch (err) {
        const failMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `❌ Index build failed: ${err}`,
            timestamp: Date.now(),
            isError: true,
        };
        chatHistory.update((h) => [...h, failMsg]);
        addToast("error", "RAG index build failed");
    } finally {
        isIndexBuilding.set(false);
    }
}

/**
 * Fetch and refresh the RAG status from the backend.
 */
export async function refreshRagStatus(): Promise<void> {
    try {
        const status = await ragStatus();
        ragStatusData.set(status);
    } catch (err) {
        console.error("Failed to fetch RAG status:", err);
        ragStatusData.set(null);
    }
}

/**
 * Clear all chat history.
 */
export function clearChat(): void {
    chatHistory.set([]);
}
