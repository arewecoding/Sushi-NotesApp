/**
 * engineSingleton.ts
 * ==================
 * Manages a single shared DrawingEngine instance for all CanvasBlock components.
 *
 * Architecture: only one engine exists; when a different block becomes active
 * the current block serializes its data, then the engine is loaded with the
 * new block's data. Unfocused blocks show a static thumbnail.
 */

import { DrawingEngine } from './engine';
import { initErrorForwarding } from './errorForwarding';

let engine: DrawingEngine | null = null;
let initPromise: Promise<DrawingEngine> | null = null;
let activeBlockId: string | null = null;

/**
 * Get (or lazily create) the shared DrawingEngine instance.
 * Safe to call from multiple blocks concurrently — only one engine is created.
 */
export async function getSharedEngine(): Promise<DrawingEngine> {
    if (engine) return engine;
    if (initPromise) return initPromise;

    initPromise = DrawingEngine.create().then(e => {
        engine = e;
        // Wire WASM error forwarding to the Python backend once on first init.
        initErrorForwarding(engine);
        return e;
    });
    return initPromise;
}

/** Return the blockId of the block that currently owns the engine, or null. */
export function getActiveBlockId(): string | null {
    return activeBlockId;
}

export function setActiveBlockId(id: string | null): void {
    console.log(`[Singleton] activeBlockId changing: ${activeBlockId} → ${id}`);
    activeBlockId = id;
}

/** Return the raw engine instance synchronously (may be null if not yet init). */
export function getEngineInstance(): DrawingEngine | null {
    return engine;
}
