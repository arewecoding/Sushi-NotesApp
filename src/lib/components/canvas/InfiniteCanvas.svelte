<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import Canvas from '$lib/canvas/Canvas.svelte';
    import CanvasToolbar from '$lib/canvas/CanvasToolbar.svelte';
    import { Expand, Shrink } from 'lucide-svelte';
    import type { Tool, BackgroundConfig } from '$lib/canvas/types';
    import { DEFAULTS } from '$lib/canvas/config';
    import { canvasInvoke } from '$lib/client/canvasApi';
    import { initErrorForwarding } from '$lib/canvas/errorForwarding';

    let { canvasId, filePath }: { canvasId: string; filePath: string } = $props();

    let canvasComponent: ReturnType<typeof Canvas> | null = $state(null);
    let isLoaded = $state(false);
    let loadError = $state<string | null>(null);
    let initialData = $state<object | null>(null);
    let autoSaveInterval: ReturnType<typeof setInterval> | null = null;

    // ── Shared canvas state ────────────────────────────────────────
    let tool: Tool = $state('pen');
    let color: string = $state(DEFAULTS.COLOR);
    let size: number = $state(DEFAULTS.STROKE_SIZE);
    let textFontSize: number = $state(DEFAULTS.FONT_SIZE);
    let bgConfig: BackgroundConfig = $state({ type: 'none', color: 'transparent', spacing: 20 });
    let activeTextStyle = $state({ fontFamily: DEFAULTS.FONT_FAMILY as string, fontSize: DEFAULTS.FONT_SIZE as number, fontWeight: DEFAULTS.FONT_WEIGHT as number, fontStyle: DEFAULTS.FONT_STYLE as string, color: DEFAULTS.COLOR as string });

    // History indicators forwarded from engine
    let canUndo = $state(false);
    let canRedo = $state(false);
    let selectedColor: string | null = $state(null);

    // Fullscreen
    let shellEl: HTMLDivElement | null = $state(null);
    let isFullscreen = $state(false);

    function toggleFullscreen() {
        if (!isFullscreen) {
            shellEl?.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    function onFullscreenChange() {
        isFullscreen = document.fullscreenElement === shellEl;
    }

    async function load() {
        try {
            const result = await canvasInvoke<{ data: object }>(
                'open_canvas_file_cmd', 
                { path: filePath }
            );
            initialData = result.data;
            isLoaded = true;
        } catch (e) {
            loadError = String(e);
        }
    }

    async function save() {
        if (!canvasComponent || !isLoaded) return;
        try {
            const serialized = canvasComponent.serialize();
            const canvasData = JSON.parse(serialized);
            await canvasInvoke('save_canvas_file_cmd', {
                fileId: canvasId,
                path: filePath,
                canvasData: canvasData
            });
        } catch (e) {
            console.error('Canvas auto-save failed:', e);
        }
    }

    onMount(async () => {
        await load();
        autoSaveInterval = setInterval(save, 30_000);
        document.addEventListener('fullscreenchange', onFullscreenChange);
    });

    onDestroy(async () => {
        if (autoSaveInterval) clearInterval(autoSaveInterval);
        document.removeEventListener('fullscreenchange', onFullscreenChange);
        await save();
    });

    // Called by Canvas.svelte once the engine is ready
    function onEngineReady(engine: unknown) {
        initErrorForwarding(engine);
    }

    function onAction(event: CustomEvent<string>) {
        if (!canvasComponent) return;
        const action = event.detail;

        if (action === 'undo' || action === 'redo' ||
            action.startsWith('color:') || action.startsWith('select:') ||
            action.startsWith('textstyle:')) {
            canvasComponent.doAction(action);
        }
    }
</script>

{#if loadError}
    <div class="canvas-error">
        <p>Failed to open canvas: {loadError}</p>
    </div>
{:else if !isLoaded}
    <div class="canvas-loading flex items-center justify-center h-full text-neutral-500">
        <p>Loading canvas...</p>
    </div>
{:else}
    <div class="infinite-canvas-shell" bind:this={shellEl}>
        <CanvasToolbar
            bind:tool
            bind:color
            bind:size
            bind:bgConfig
            bind:activeTextStyle
            {canUndo}
            {canRedo}
            {selectedColor}
            on:action={onAction}
        />
        <div class="canvas-area relative flex-grow min-h-0 overflow-hidden">
            <Canvas
                bind:this={canvasComponent}
                {initialData}
                {onEngineReady}
                bind:tool
                bind:color
                bind:size
                bind:selectedColor
                bind:textFontSize
                bind:bgConfig
                bind:activeTextStyle
                on:historychange={(e) => {
                    // Update undo/redo from the engine event
                    canUndo = e.detail.canUndo;
                    canRedo = e.detail.canRedo;
                }}
            />
            <button
                class="fullscreen-btn"
                onclick={toggleFullscreen}
                title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            >
                {#if isFullscreen}
                    <Shrink size={16} />
                {:else}
                    <Expand size={16} />
                {/if}
            </button>
        </div>
    </div>
{/if}

<style>
    .infinite-canvas-shell {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        overflow: hidden;
    }

    .fullscreen-btn {
        position: absolute;
        top: 0.75rem;
        right: 0.75rem;
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        background: rgba(30, 30, 30, 0.85);
        border: 1px solid #444;
        border-radius: 6px;
        padding: 0;
        cursor: pointer;
        color: #a3a3a3;
        transition: background 0.15s ease, color 0.15s ease;
    }

    .fullscreen-btn:hover {
        background: #262626;
        color: #f5f5f5;
    }
</style>
