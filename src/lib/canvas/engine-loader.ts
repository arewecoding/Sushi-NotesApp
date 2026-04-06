let wasmModule: typeof import('$canvas-engine') | null = null;

async function loadWasm() {
    if (wasmModule) return wasmModule;
    const wasm = await import('$canvas-engine');
    await wasm.default();
    wasmModule = wasm;
    return wasm;
}

export async function createEngineInstance() {
    const wasm = await loadWasm();
    return new wasm.CanvasEngine();
}
