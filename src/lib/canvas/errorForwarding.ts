/**
 * Canvas Error Forwarding
 * ========================
 * Forwards WASM engine errors and unhandled JS rejections to the Python
 * backend via the log_error_cmd IPC command for centralized logging.
 */

import { canvasInvoke } from "$lib/client/canvasApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let engine: any = null;

/**
 * Start polling the WASM engine for errors and forwarding them to Python.
 * Call this when the canvas engine is first instantiated.
 * @param canvasEngine - The WASM CanvasEngine instance
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function initErrorForwarding(canvasEngine: any): void {
    engine = canvasEngine;

    // Forward WASM errors to Python every 10 seconds
    setInterval(async () => {
        if (!engine) return;
        try {
            const err = engine.get_last_error?.();
            if (err) {
                await canvasInvoke("log_error_cmd", {
                    source: "rust_wasm",
                    message: err,
                    timestamp: new Date().toISOString(),
                });
                engine.clear_last_error?.();
            }
        } catch {
            // Silently ignore — don't let error forwarding cause errors
        }
    }, 10_000);
}

/**
 * Register a global handler for unhandled promise rejections.
 * Forwards them to the Python backend for centralized logging.
 * Call this once at app startup (in the root layout's onMount).
 */
export function initGlobalErrorHandler(): void {
    window.addEventListener("unhandledrejection", async (event) => {
        try {
            await canvasInvoke("log_error_cmd", {
                source: "svelte",
                message: event.reason?.toString() ?? "unknown unhandled rejection",
                stack: event.reason?.stack ?? null,
                timestamp: new Date().toISOString(),
            });
        } catch {
            // Silently ignore
        }
    });
}
