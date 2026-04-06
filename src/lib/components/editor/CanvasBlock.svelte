<script lang="ts">
    /**
     * CanvasBlock.svelte
     * ==================
     * An embedded canvas block inside the Sushi Notes rich-text editor.
     *
     * Architecture: singleton engine with page-swapping.
     * One DrawingEngine instance is shared across all blocks. When this block
     * gains focus it loads its stored data into the engine. On blur it serializes
     * the state and saves it to disk alongside a thumbnail. Unfocused blocks
     * show a static thumbnail.
     *
     * Wiring mirrors InfiniteCanvas.svelte exactly — do not deviate from that
     * proven pattern.
     *
     * States:
     *   "thumbnail" — not focused, static thumbnail shown
     *   "loading"   — focused, engine or data loading
     *   "active"    — focused, drawing surface live
     *   "saving"    — blur fired, save + thumbnail in flight
     */
    import { onMount, onDestroy, tick } from 'svelte';
    import { PenLine } from 'lucide-svelte';
    import Canvas from '$lib/canvas/Canvas.svelte';
    import CanvasToolbar from '$lib/canvas/CanvasToolbar.svelte';
    import {
        getSharedEngine,
        getActiveBlockId,
        setActiveBlockId,
    } from '$lib/canvas/engineSingleton';
    import { canvasInvoke } from '$lib/client/canvasApi';
    import { getResourcePath } from '$lib/client/apiClient';
    import { convertFileSrc } from '@tauri-apps/api/core';
    import { activeNoteId } from '$lib/stores/notesStore';
    import type { Tool, BackgroundConfig } from '$lib/canvas/types';
    import { DEFAULTS } from '$lib/canvas/config';

    // ── Props ─────────────────────────────────────────────────────────────────
    let {
        blockId,
        noteId,
        initialData,
        onchange,
    }: {
        blockId: string;
        noteId: string;
        initialData: {
            canvas_ref?: string;
            thumbnail_ref?: string;
            size?: { preset: string; width_mm: number; height_mm: number };
        };
        onchange: (blockId: string, newData: object) => void;
    } = $props();

    // ── Stable canvas-ref: a UUID filename, stable across saves ───────────────
    const defaultCanvasRef = initialData.canvas_ref ?? `${crypto.randomUUID()}.jcanvas`;
    const defaultThumbRef = initialData.thumbnail_ref ?? null;

    let canvasRef = $state(defaultCanvasRef);
    let thumbnailRef = $state<string | null>(defaultThumbRef);
    let thumbnailSrc = $state<string | null>(null);

    $effect(() => {
        if (thumbnailRef && noteId) {
                getResourcePath(noteId, thumbnailRef, blockId, initialData).then(result => {
                    if (typeof result === 'string') {
                        // Append cache-buster so the browser reloads the updated thumbnail image after a save
                        thumbnailSrc = `${convertFileSrc(result)}?t=${Date.now()}`;
                    } else if (result?.status === 'regeneration_required') {
                        regenerateThumbnail(result.canvasData, result.lastViewport);
                    }
                });
        } else {
            // Null thumbnailRef means static placeholder
            thumbnailSrc = null;
        }
    });

    // ── In-Memory Snapshot & Autosave State ───────────────────────────────
    let snapshotDataUrl = $state<string | null>(null);
    let latestCanvasData = $state<object | null>(null);
    
    let isDirty = $state(false);
    let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

    // ── Block UI state ─────────────────────────────────────────────────────────
    type BlockState = 'thumbnail' | 'loading' | 'active' | 'regenerating';
    let blockState = $state<BlockState>('thumbnail');

    async function regenerateThumbnail(canvasData: any, lastViewport: any) {
        if (!canvasRef || !noteId) return;
        
        blockState = 'regenerating';
        await tick();
        await tick();

        if (canvasComponent) {
            canvasComponent.deserialize(JSON.stringify(canvasData));
            // Let the canvas render the strokes
            await new Promise(r => requestAnimationFrame(r));
            await new Promise(r => requestAnimationFrame(r));
            
            const dataUrl = await canvasComponent.generateThumbnail();
            
            await canvasInvoke('save_canvas_block_cmd', {
                noteId: $activeNoteId,
                blockId,
                canvasRef,
                canvasData: canvasData,
                thumbnailDataUrl: dataUrl
            });
            
            // Re-trigger load
            const tRef = initialData.thumbnail_ref;
            if (tRef) {
                getResourcePath(noteId, tRef, blockId, initialData).then(result => {
                    if (typeof result === 'string') {
                        thumbnailSrc = `${convertFileSrc(result)}?t=${Date.now()}`;
                    }
                });
            }
            
            canvasComponent.clearEngine();
        }
        
        blockState = 'thumbnail';
    }

    // ── Canvas tool state — mirrors InfiniteCanvas.svelte ─────────────────────
    let tool: Tool = $state('pen');
    let color: string = $state(DEFAULTS.COLOR);
    let size: number = $state(DEFAULTS.STROKE_SIZE);
    let textFontSize: number = $state(DEFAULTS.FONT_SIZE);
    let bgConfig: BackgroundConfig = $state({ type: 'none', color: 'transparent', spacing: 20 });
    let activeTextStyle = $state({
        fontFamily: DEFAULTS.FONT_FAMILY as string,
        fontSize: DEFAULTS.FONT_SIZE as number,
        fontWeight: DEFAULTS.FONT_WEIGHT as number,
        fontStyle: DEFAULTS.FONT_STYLE as string,
        color: DEFAULTS.COLOR as string,
    });
    let canUndo = $state(false);
    let canRedo = $state(false);
    let selectedColor: string | null = $state(null);

    // ── DOM / component refs ───────────────────────────────────────────────────
    let containerEl = $state<HTMLDivElement | null>(null);
    let canvasComponent: ReturnType<typeof Canvas> | null = $state(null);

    // ── Emergency flush helper (sync, fire-and-forget) ──────────────────────
    function emergencyFlush() {
        if (latestCanvasData && canvasRef && noteId) {
            canvasInvoke('save_canvas_block_cmd', {
                noteId,
                blockId,
                canvasRef,
                canvasData: latestCanvasData,
                thumbnailDataUrl: null,
            }).catch((e: unknown) => {
                console.error('[CanvasBlock] emergency save failed:', e);
            });
        }
    }

    // ── App close flush ────────────────────────────────────────────────────
    function handleBeforeClose() {
        emergencyFlush();
    }

    onMount(() => {
        // Ensure new blocks immediately commit their stable refs to the note JSON
        // so that if the user closes the app before blurring, the refs are not lost.
        onchange(blockId, {
            canvas_ref: canvasRef,
            thumbnail_ref: thumbnailRef,
            size: initialData.size,
        });

        // Listen for app close signal from +layout.svelte
        window.addEventListener('sushi:beforeclose', handleBeforeClose);
    });

    onDestroy(() => {
        // Unregister close listener to prevent leaks
        window.removeEventListener('sushi:beforeclose', handleBeforeClose);

        // Cancel pending debounce timer
        if (saveDebounceTimer) clearTimeout(saveDebounceTimer);

        // Emergency flush using cached data — do NOT call canvasComponent.serialize()
        // because Svelte does not await async onDestroy callbacks and the child
        // Canvas component may already be destroyed by this point.
        emergencyFlush();

        if (getActiveBlockId() === blockId) {
            setActiveBlockId(null);
        }
    });

    // ── onAction — mirrors InfiniteCanvas.onAction exactly ────────────────────
    function onAction(event: CustomEvent<string>) {
        if (!canvasComponent) return;
        const action = event.detail;
        if (
            action === 'undo' || action === 'redo' ||
            action.startsWith('color:') ||
            action.startsWith('select:') ||
            action.startsWith('textstyle:')
        ) {
            canvasComponent.doAction(action);
        }
    }

    // ── AUTOSAVE (Flusher) ────────────────────────────────────────────────────
    async function flushSave(includeThumbnail: boolean, force = false) {
        if ((!isDirty && !force) || !canvasComponent || !noteId) return;
        
        isDirty = false;
        try {
            const serialized = canvasComponent.serialize();
            if (serialized) {
                const canvasData = JSON.parse(serialized);
                latestCanvasData = canvasData; // Keep JSON in memory for fast focus switches

                let thumbDataUrl: string | undefined = undefined;
                if (includeThumbnail) {
                    thumbDataUrl = await canvasComponent.generateThumbnail();
                }

                const result = await canvasInvoke<{ thumbnail_ref: string }>(
                    'save_canvas_block_cmd',
                    {
                        noteId,
                        blockId,
                        canvasRef,
                        canvasData,
                        thumbnailDataUrl: thumbDataUrl || null,
                    }
                );

                if (result.thumbnail_ref) {
                    thumbnailRef = result.thumbnail_ref;
                    onchange(blockId, {
                        canvas_ref: canvasRef,
                        thumbnail_ref: thumbnailRef,
                        size: initialData.size,
                    });
                }
            }
        } catch (e) {
            console.error('[CanvasBlock] auto save failed:', e);
            isDirty = true; // Revert dirty flag so next debounce catches it
        }
    }

    function handleHistoryChange(e: CustomEvent) {
        canUndo = e.detail.canUndo;
        canRedo = e.detail.canRedo;
        if (blockState !== 'active') return;

        isDirty = true;
        if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
        saveDebounceTimer = setTimeout(() => flushSave(true), 2000);
    }

    // ── FOCUS — become the active block ───────────────────────────────────────
    async function onFocusIn() {
        console.log(`[CanvasBlock ${blockId}] onFocus fired. current blockState=${blockState}`);
        if (blockState === 'active' || blockState === 'loading') return;
        
        containerEl?.focus();
        blockState = 'loading';
        setActiveBlockId(blockId);

        await getSharedEngine();

        // 1. Try to load from in-memory cache first (super fast)
        let dataToLoad = latestCanvasData;
        
        // 2. Fall back to backend if cache is empty
        const noteId = $activeNoteId;
        if (!dataToLoad && noteId) {
            try {
                const result = await canvasInvoke<{ data: object | null }>(
                    'load_canvas_block_cmd',
                    { noteId, canvasRef }
                );
                dataToLoad = result.data ?? null;
                latestCanvasData = dataToLoad;
            } catch (e) {
                console.error('[CanvasBlock] load failed:', e);
            }
        }

        // We can discard snapshotDataUrl to free memory when block is active
        snapshotDataUrl = null;

        blockState = 'active';
        await tick();
        await tick();

        if (canvasComponent) {
            if (dataToLoad) {
                canvasComponent.deserialize(JSON.stringify(dataToLoad));
            } else {
                // Clear the engine for this new blank block!
                canvasComponent.clearEngine();
            }
        }
    }

    // ── BLUR — serialize, save, thumbnail ─────────────────────────────────────
    async function onFocusOut(e: FocusEvent) {
        // Ignore focus moving within this block (toolbar buttons etc.)
        const related = e.relatedTarget as HTMLElement | null;
        if (related && containerEl?.contains(related)) return;
        if (getActiveBlockId() !== blockId) return;

        if (canvasComponent) {
            // 1. Capture pixel-accurate snapshot first before clearing anything
            snapshotDataUrl = await canvasComponent.generateThumbnail();

            // 2. Trigger a forced save flush (even if debounce already fired, we need the thumbnail)
            await flushSave(true, true);

            // 3. Clear engine explicitly (no JSON overhead)
            canvasComponent.clearEngine();
        }

        // Always ensure we release ownership and return to thumbnail (hidden active canvas)
        if (getActiveBlockId() === blockId) {
            setActiveBlockId(null);
        }
        blockState = 'thumbnail';
    }

    onDestroy(() => {
        // Cancel pending debounce timer
        if (saveDebounceTimer) clearTimeout(saveDebounceTimer);

        // Emergency flush using cached data — do NOT call canvasComponent.serialize()
        // because Svelte does not await async onDestroy callbacks and the child
        // Canvas component may already be destroyed by this point.
        if (latestCanvasData && canvasRef && $activeNoteId) {
            canvasInvoke('save_canvas_block_cmd', {
                noteId: $activeNoteId,
                blockId,
                canvasRef,
                canvasData: latestCanvasData,
                thumbnailDataUrl: null,
            }).catch((e: unknown) => {
                console.error('[CanvasBlock] emergency save failed:', e);
            });
        }

        if (getActiveBlockId() === blockId) {
            setActiveBlockId(null);
        }
    });
</script>

<!--
    tabindex="0" makes the container focusable so MainArea's block-wrapper
    onfocusin fires. Do NOT stopPropagation — MainArea needs focusin to bubble.
-->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
    bind:this={containerEl}
    class="canvas-block-container"
    tabindex="0"
    onfocusin={onFocusIn}
    onfocusout={onFocusOut}
>
    {#if blockState === 'thumbnail'}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class="canvas-thumbnail"
            onclick={onFocusIn}
            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') onFocusIn(); }}
            role="button"
            tabindex="0"
        >
            {#if snapshotDataUrl || thumbnailSrc}
                <img src={snapshotDataUrl || thumbnailSrc} alt="Canvas block" class="thumb-img" />
            {:else}
                <div class="thumb-empty">
                    <PenLine size={20} />
                    <span>Click to draw</span>
                </div>
            {/if}
        </div>

    {:else if blockState === 'loading'}
        <div class="canvas-status">
            <span>Loading canvas…</span>
        </div>

    {:else if blockState === 'active' || blockState === 'regenerating'}
        <!-- When regenerating, keep it in DOM but hidden so Canvas computes correctly -->
        <div class="canvas-active-shell" style={blockState === 'regenerating' ? 'position: absolute; opacity: 0; pointer-events: none; z-index: -100;' : ''}>
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
                    on:historychange={handleHistoryChange}
                />
            </div>
        </div>

    {/if}
</div>

<style>
    .canvas-block-container {
        width: 100%;
        outline: none;
        border: 1px solid #2a2a2a;
        border-radius: 6px;
        overflow: hidden;
        margin: 0.5rem 0;
        background: #111;
        transition: border-color 0.15s ease;
    }

    .canvas-block-container:focus-within {
        border-color: #444;
    }

    .canvas-active-shell {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 520px;
    }

    .canvas-area {
        flex: 1;
        min-height: 0;
        position: relative;
        overflow: hidden;
    }

    .canvas-thumbnail {
        width: 100%;
        min-height: 160px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #111;
        transition: background 0.15s ease;
    }

    .canvas-thumbnail:hover {
        background: #1a1a1a;
    }

    .thumb-img {
        width: 100%;
        display: block;
        object-fit: cover;
        max-height: 320px;
    }

    .thumb-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        color: #404040;
        font-size: 0.85rem;
        padding: 2.5rem;
        font-family: 'Inter', system-ui, sans-serif;
        user-select: none;
    }

    .canvas-status {
        height: 160px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #404040;
        font-size: 0.85rem;
        font-family: 'Inter', system-ui, sans-serif;
    }
</style>
