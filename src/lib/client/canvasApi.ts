/**
 * Canvas API Client
 * ==================
 * Typed wrapper for canvas-related IPC calls using the ok/err envelope protocol.
 * All canvas IPC should go through canvasInvoke<T>() — never raw pyInvoke.
 */

import { pyInvoke } from "tauri-plugin-pytauri-api";

type ApiResponse<T> =
    | { status: "ok"; data: T }
    | { status: "error"; code: string; message: string };

function canvasErrorHandler(code: string, message: string): void {
    console.error(`[Canvas API ${code}]: ${message}`);
    // TODO: wire to a toast store when one exists
}

/**
 * Invoke a canvas-related Python IPC command with envelope unwrapping.
 * Returns the data payload on success, throws on error.
 * @param command - The Python IPC command name (e.g. "log_error_cmd")
 * @param payload - The request payload (will be serialized as camelCase)
 */
export async function canvasInvoke<T = unknown>(
    command: string,
    payload?: unknown
): Promise<T> {
    const response = await pyInvoke<ApiResponse<T>>(command, payload ?? {});
    if (response.status === "error") {
        canvasErrorHandler(response.code, response.message);
        throw new Error(`[${response.code}] ${response.message}`);
    }
    return response.data;
}
