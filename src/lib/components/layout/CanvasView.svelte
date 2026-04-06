<script lang="ts">
    /**
     * CanvasView.svelte
     * =================
     * Tab content wrapper that orchestrates the Canvas drawing surface and
     * its toolbar. Replicates the standalone Canvas app's +page.svelte
     * wiring pattern: local state for tool/color/size, two-way bindings
     * to both Canvas and CanvasToolbar, and action dispatch.
     */
    import Canvas from '$lib/canvas/Canvas.svelte';
    import CanvasToolbar from '$lib/canvas/CanvasToolbar.svelte';
    import type { Tool, BackgroundConfig } from '$lib/canvas/types';
    import { DEFAULTS } from '$lib/canvas/config';
    import { initFlags } from '$lib/canvas/stores';
    import { onMount } from 'svelte';

    // ── Shared canvas state ────────────────────────────────────────
    let tool: Tool = 'pen';
    let color: string = DEFAULTS.COLOR;
    let size: number = DEFAULTS.STROKE_SIZE;
    let textFontSize: number = DEFAULTS.FONT_SIZE;
    let bgConfig: BackgroundConfig = { type: 'none', color: '#d0d0d0', spacing: 20 };
    let activeTextStyle = { fontFamily: DEFAULTS.FONT_FAMILY as string, fontSize: DEFAULTS.FONT_SIZE as number, fontWeight: DEFAULTS.FONT_WEIGHT as number, fontStyle: DEFAULTS.FONT_STYLE as string, color: DEFAULTS.COLOR as string };

    // History indicators forwarded from engine
    let canUndo = false;
    let canRedo = false;
    let selectedColor: string | null = null;

    // Canvas component ref for imperative calls
    let canvasComponent: Canvas;
    let serializeSize = 0;

    onMount(() => {
        initFlags();
    });

    function onAction(event: CustomEvent<string>) {
        if (!canvasComponent) return;
        const action = event.detail;

        if (action === 'undo' || action === 'redo' ||
            action.startsWith('color:') || action.startsWith('select:') ||
            action.startsWith('textstyle:')) {
            canvasComponent.doAction(action);
        }
        console.log('[DEBUG-Serialize]', canvasComponent.serialize().slice(0, 300));
    }


</script>

<div class="canvas-view">
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
    <div class="canvas-area">
        <Canvas
            bind:this={canvasComponent}
            bind:tool
            bind:color
            bind:size
            bind:selectedColor
            bind:textFontSize
            bind:bgConfig
            bind:activeTextStyle
            on:historychange={(e) => {
                canUndo = e.detail.canUndo;
                canRedo = e.detail.canRedo;
                serializeSize = canvasComponent.serialize().length;
            }}
        />
    </div>
    
    <!-- DEBUG OVERLAY -->
    <div style="position: absolute; bottom: 10px; left: 10px; background: rgba(0,0,0,0.8); color: lime; padding: 10px; font-family: monospace; z-index: 9999;">
        Serialized Length: {serializeSize} bytes
    </div>
</div>

<style>
    .canvas-view {
        flex-grow: 1;
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        overflow: hidden;
    }

    .canvas-area {
        flex: 1;
        position: relative;
        overflow: hidden;
        min-height: 0;
    }
</style>
