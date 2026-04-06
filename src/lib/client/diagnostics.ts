import { pyInvoke } from "tauri-plugin-pytauri-api";

interface LogMessage {
    level: string;
    message: string;
    timestamp: number;
}

let queue: LogMessage[] = [];
let isReady = false;

function processLog(msg: any): string {
    if (msg instanceof Error) return msg.stack || msg.message;
    if (typeof msg === 'object') {
        try {
            return JSON.stringify(msg);
        } catch {
            return String(msg);
        }
    }
    return String(msg);
}

export function initDiagnosticsPiping() {
    if ((window as any).__DIAGNOSTICS_INIT__) return;
    (window as any).__DIAGNOSTICS_INIT__ = true;

    const originalConsole = {
        log: console.log,
        warn: console.warn,
        error: console.error,
        info: console.info,
        debug: console.debug
    };

    function override(level: keyof typeof originalConsole) {
        console[level] = (...args: any[]) => {
            originalConsole[level](...args);
            
            const message = args.map(processLog).join(" ");
            const logMsg = {
                level,
                message,
                timestamp: Date.now() / 1000.0,
            };

            if (!isReady || queue.length > 0) {
                queue.push(logMsg);
            } else {
                sendToBackend(logMsg);
            }
        };
    }

    override('log');
    override('warn');
    override('error');
    override('info');
    override('debug');

    // Attempt to flush queue periodically until IPC works
    const flushInterval = setInterval(async () => {
        if (queue.length === 0) return;
        // Basic check if Tauri is injected
        if (!(window as any).__TAURI_INTERNALS__ && !(window as any).__TAURI_IPC__) return;

        isReady = true;
        const currentQueue = [...queue];
        queue = [];

        for (const logMsg of currentQueue) {
            await sendToBackend(logMsg);
        }
    }, 500);
}

async function sendToBackend(logMsg: LogMessage) {
    try {
        await pyInvoke("frontend_log_cmd", logMsg);
    } catch (e) {
        // Fallback: push back to queue if IPC fails temporarily during startup
        if (String(e).includes("IPC")) {
            queue.unshift(logMsg);
            isReady = false;
        }
    }
}
