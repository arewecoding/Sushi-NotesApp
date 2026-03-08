/**
 * ragApiClient.ts
 * ===============
 * Type-safe wrappers for the three RAG IPC commands:
 *   rag_query, rag_build_index, rag_status
 */

import { pyInvoke } from "tauri-plugin-pytauri-api";
import type { InvokeOptions } from "@tauri-apps/api/core";

// ── Types ─────────────────────────────────────────────────────────────────

export interface RagQueryRequest {
    query: string;
}

export interface RagQueryResponse {
    answer: string;
    strategy: string;
    queryOriginal: string;
    queryOptimized: string;
    blocksRetrieved: number;
    blocksReranked: number;
    blocksInContext: number;
    contextTruncated: boolean;
    latency: Record<string, number>;
    ragEnabled: boolean;
}

export interface RagBuildIndexResponse {
    status: string;
    notesIndexed: number;
    blocksIndexed: number;
    graphNodes: number;
    graphEdges: number;
    ragEnabled: boolean;
    message: string;
}

export interface RagStatusResponse {
    ragEnabled: boolean;
    faissVectors: number;
    tombstoneRatio: number;
    graphNodes: number;
    graphEdges: number;
    message: string;
}

// ── Functions ─────────────────────────────────────────────────────────────

/**
 * Run the full GraphRAG pipeline for a natural-language query.
 * May take 2–10 seconds (Gemini API calls). Show a loading indicator.
 */
export async function ragQuery(
    query: string,
    options?: InvokeOptions
): Promise<RagQueryResponse> {
    return await pyInvoke("rag_query", { query }, options);
}

/**
 * Trigger a full rebuild of the RAG index over the entire vault.
 * Calls Gemini embeddings for every block — can take minutes on large vaults.
 */
export async function ragBuildIndex(
    options?: InvokeOptions
): Promise<RagBuildIndexResponse> {
    return await pyInvoke("rag_build_index", {}, options);
}

/**
 * Return a health snapshot of the RAG index (fast, no API calls).
 */
export async function ragStatus(
    options?: InvokeOptions
): Promise<RagStatusResponse> {
    return await pyInvoke("rag_status", {}, options);
}
