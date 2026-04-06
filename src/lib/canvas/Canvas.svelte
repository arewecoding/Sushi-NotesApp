<script lang="ts">
  import { onMount, onDestroy, tick, createEventDispatcher } from 'svelte';
  import { DrawingEngine } from './engine';
  import { renderFrame, renderActiveLayer } from './renderer';
  import type { Tool, RenderState, ImageObjectData, BackgroundConfig } from './types';
  import { RENDER, DEFAULTS, INTERACTION } from './config';
  import { getCoalescedPoints, normalizePointerEvent } from './input';
  import { setupShortcuts } from './shortcuts';
  import { importCanvasImage, getResourceBytes } from './client/canvas';
  import { featureFlags } from './stores';

  export let tool: Tool = 'pen';
  export let color: string = '#000000';
  export let size: number = 4;
  let canUndo: boolean = false;
  let canRedo: boolean = false;
  export let selectedColor: string | null = null;
  export let textFontSize: number = DEFAULTS.FONT_SIZE;
  export let canvasFilePath: string | null = null;
  export let initialData: Record<string, any> | null = null;
  export let onEngineReady: ((engine: any) => void) | null = null;

  const dispatch = createEventDispatcher<{
    historychange: { canUndo: boolean, canRedo: boolean };
    action: string;
  }>();

  let bgCanvas: HTMLCanvasElement;
  let bgCtx: CanvasRenderingContext2D | null = null;
  export let bgConfig: BackgroundConfig = { type: 'none', color: '#d0d0d0', spacing: 20 };

  let baseCanvas: HTMLCanvasElement;
  let activeCanvas: HTMLCanvasElement;
  let engine: DrawingEngine;
  let animFrameId: number;
  let isDirty = false;
  function markDirty(base = true) {
    isDirty = true;
    if (base && renderState) renderState.baseDirty = true;
  }
  let cleanupShortcuts: () => void;
  let currentViewport: [number, number, number] = [0, 0, 1];
  let rawPointerScreen = { x: 0, y: 0 };
  import { GestureHandler } from './tools';
  let gestureHandler: GestureHandler;
  let isPanning = false;
  let lastPointerType: string | null = null;

  let stylusActive = false;
  let stylusDeactivateTimer: ReturnType<typeof setTimeout> | null = null;
  const PALM_REJECT_TIMEOUT = 500;
  
  let usingTemporaryTool = false;
  let previousTool: string | null = null;

  // Text editing state
  import { TextEditorHandler } from './tools';
  let textHandler: TextEditorHandler;
  let textOverlayState: any = null;
  function syncTextOverlay() {
    if (textHandler) {
      textOverlayState = textHandler.getState();
      if (renderState) renderState.editingTextId = textOverlayState.editingTextId;
    }
  }

  function attachTextEditor(node: HTMLElement) {
    textHandler.attachEditorEl(node);
    return { destroy() { textHandler.attachEditorEl(null); } };
  }

  let selectionState: any = null;
  function syncSelectionState() {
     if (selectionHandler) selectionState = selectionHandler.getState();
  }

  // Single Source of Truth: reactively derive font size during live scaling preview
  $: if (selectionState && selectionState.mode === 'resizing' && selectionState.liveTransform && engine) {
      const selectedTextId = engine.getSelectedTextId();
      if (selectedTextId !== -1) {
          try {
              const objStr = engine.getTextObject(selectedTextId);
              const obj = JSON.parse(objStr);
              if (obj && obj.font_size) {
                  const liveSize = Math.max(8, Math.round(obj.font_size * Math.abs(selectionState.liveTransform.scaleY)));
                  if (activeTextStyle.fontSize !== liveSize) {
                      activeTextStyle.fontSize = liveSize;
                  }
              }
          } catch (_) {}
      }
  }

  // Persistent text style state (survives tool switches)
  export let activeTextStyle = { fontFamily: DEFAULTS.FONT_FAMILY as string, fontSize: DEFAULTS.FONT_SIZE as number, fontWeight: DEFAULTS.FONT_WEIGHT as number, fontStyle: DEFAULTS.FONT_STYLE as string, color: DEFAULTS.COLOR as string };

  import { SelectionHandler } from './tools';
  let selectionHandler: SelectionHandler;
  let hoverCursor: string = 'default';
  let preDragColorState: string | null = null;

  let renderState: RenderState;

  // Track the reactive props and apply them to engine when they change
  $: if (engine && renderState) {
    handleToolChange(actionCtx, { tool, color, size, renderState });
  }

  $: if (textHandler && currentViewport && textHandler.getState().editingTextId !== null) {
    textHandler.updateViewport(currentViewport);
    syncTextOverlay();
  }

  onMount(async () => {
    console.log(`[Canvas] onMount fired. baseCanvas dimensions: ${baseCanvas?.width}x${baseCanvas?.height}, container: ${baseCanvas?.parentElement?.getBoundingClientRect().width}x${baseCanvas?.parentElement?.getBoundingClientRect().height}`);
    engine = await DrawingEngine.create();
    if (onEngineReady) onEngineReady(engine);
    
    if (initialData) {
        try {
            engine.deserialize(JSON.stringify(initialData));
            if (initialData.background) {
                bgConfig = initialData.background as BackgroundConfig;
            }
            if (initialData.viewport) {
                currentViewport = [
                    initialData.viewport.offset_x || 0,
                    initialData.viewport.offset_y || 0,
                    initialData.viewport.scale || 1
                ];
            }
        } catch (e) {
            console.error("Canvas deserialize failed:", e);
        }
    }

    featureFlags.subscribe(flags => {
      if (engine) engine.setFeatureFlags(JSON.stringify(flags));
    });

    selectionHandler = new SelectionHandler(engine);
    textHandler = new TextEditorHandler(engine);
    textHandler.onAsyncCommit = () => {
      syncTextOverlay();
      updateHistoryState();
      markDirty(true);
    };
    gestureHandler = new GestureHandler(engine);
    syncTextOverlay();
    
    bgCtx = bgCanvas?.getContext('2d')!;
    
    // Set initial configuration
    engine.setTool(tool);
    engine.setColor(color);
    engine.setSize(size);
    
    renderState = {
      baseCtx: baseCanvas.getContext('2d')!,
      activeCtx: activeCanvas.getContext('2d')!,
      objects: engine.getAllObjects(),
      activeOutline: null,
      activeColor: color,
      activeOpacity: tool === 'highlighter' ? 0.5 : 1.0,
      activeTool: tool,
      eraserPos: null,
      rawPointerScreen: rawPointerScreen,
      eraserRadius: size,
      highlightedIds: new Set(),
      selectionBounds: null,
      liveTransform: null,
      selectedIds: new Set(),
      marqueeRect: null,
      baseDirty: true,
      selectedTextId: -1,
      editingTextId: null,
      imageCache: new Map(),
    };

    cleanupShortcuts = setupShortcuts(engine, doAction);

    setupDPR();
    startRenderLoop();
    setupResizeObserver();
  });

  let resizeObserver: ResizeObserver | null = null;
  onDestroy(() => {
    if (animFrameId) cancelAnimationFrame(animFrameId);
    if (cleanupShortcuts) cleanupShortcuts();
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
  });

  function setupDPR() {
    if (!baseCanvas) return;
    const dpr = window.devicePixelRatio ?? 1;
    const rect = baseCanvas.getBoundingClientRect();
    baseCanvas.width = rect.width * dpr;
    baseCanvas.height = rect.height * dpr;
    activeCanvas.width = rect.width * dpr;
    activeCanvas.height = rect.height * dpr;
    if (bgCanvas) {
      bgCanvas.width = rect.width * dpr;
      bgCanvas.height = rect.height * dpr;
      if (bgCtx) renderBackground(bgConfig, currentViewport);
    }
    markDirty(true);
  }

  function setupResizeObserver() {
    resizeObserver = new ResizeObserver(() => {
      if (!baseCanvas) return;
      setupDPR();
      console.log(`[Canvas] ResizeObserver fired. new dimensions: ${baseCanvas?.width}x${baseCanvas?.height}`);
    });
    resizeObserver.observe(baseCanvas);
  }

  function forceRender() {
    if (isDirty && renderState) {
      const boundsUpdates = renderFrame(renderState, currentViewport);
      let boundsChanged = false;
      for (const { id, w, h } of boundsUpdates) {
        engine.updateTextBounds(id, w, h);
        boundsChanged = true;
      }
      if (boundsChanged && engine.hasSelection()) {
        // Refresh selection bounds so the dashed box matches updated text dimensions
        const b = engine.getSelectionBounds();
        renderState.selectionBounds = b
          ? { x: b[0], y: b[1], w: b[2] - b[0], h: b[3] - b[1] }
          : renderState.selectionBounds;
        // Re-render the active layer (selection handles) with the corrected bounds
        renderActiveLayer(renderState.activeCtx, renderState, currentViewport);
      }
      isDirty = false;
    }
  }

  function startRenderLoop() {
    function loop() {
      forceRender();
      animFrameId = requestAnimationFrame(loop);
    }
    animFrameId = requestAnimationFrame(loop);
  }

  function updateHistoryState() {
    if (!engine || !renderState) return;
    renderState.objects = engine.getAllObjects();
    renderState.selectedTextId = engine.getSelectedTextId();
    canUndo = engine.canUndo();
    canRedo = engine.canRedo();
    dispatch('historychange', { canUndo, canRedo });
    markDirty(true);
  }

  import { handlePointerDown, handlePointerMove, handlePointerUp, getCursorForTool, handleDeviceChanged, handleToolChange, dispatchAction } from './actions';
  
  $: actionCtx = {
    get engine() { return engine!; },
    get viewport() { return currentViewport; },
    get activeTool() { return tool; },
    get selectionHandler() { return selectionHandler; },
    get textHandler() { return textHandler; },
    get activeTextStyle() { return activeTextStyle; },
    updateTextStyle: (style: Partial<typeof activeTextStyle>) => {
      activeTextStyle = { ...activeTextStyle, ...style };
      if (style.color) color = style.color;
    },
    getSize: () => size,
    requestRedraw: (baseLayer?: boolean) => markDirty(baseLayer),
    updateHistory: () => updateHistoryState(),
    syncState: () => {
        syncSelectionState();
        syncTextOverlay();
        refreshRenderState();
        updateSelectionRenderState();
    },
    updateTextSize: (s: number) => { textFontSize = s; },
    setHoverCursor: (c: string) => { hoverCursor = c; },
    setEraserPos: (pos: any) => { if (renderState) renderState.eraserPos = pos; },
    setActiveOutline: (outline: any) => { if (renderState) renderState.activeOutline = outline; },
    setShiftHeld: (held: boolean) => { if (renderState) renderState.shiftHeld = held; },
    onShapeDetected: $featureFlags.enable_shape_recognition !== false ? (shapeJson: string, strokeId: number) => {
      showShapeToast(shapeJson, Math.round(strokeId));
    } : undefined
  } as import('./actions').ActionContext;

  async function onDeviceChanged(pointerType: string) {
    if (!engine) return;
    await handleDeviceChanged(actionCtx, pointerType);
  }

  function refreshRenderState() {
    if (!engine || !renderState) return;
    renderState.objects = engine.getAllObjects();
    renderState.selectedTextId = engine.getSelectedTextId();
  }

  function updateSelectionRenderState() {
    syncSelectionState();
    if (!engine || !renderState) return;
    const rawIds = engine.getSelectedIds();
    renderState.selectedIds = new Set<number>(Array.from(rawIds).map(Number));
    const b = engine.getSelectionBounds();
    renderState.selectionBounds = b
      ? { x: b[0], y: b[1], w: b[2] - b[0], h: b[3] - b[1] }
      : null;
    selectedColor = rawIds.length > 0 ? (engine.getSelectedColor() ?? 'mixed') : null;
    
    if (selectionHandler) {
      const st = selectionHandler.getState();
      renderState.liveTransform = st.liveTransform;
      if (st.mode === 'marquee' && st.marqueeStart && st.marqueeEnd) {
        renderState.marqueeRect = {
          x: Math.min(st.marqueeStart.x, st.marqueeEnd.x),
          y: Math.min(st.marqueeStart.y, st.marqueeEnd.y),
          w: Math.abs(st.marqueeStart.x - st.marqueeEnd.x),
          h: Math.abs(st.marqueeStart.y - st.marqueeEnd.y),
        };
      } else {
        renderState.marqueeRect = null;
      }
    }
    markDirty(false);
  }

  function onPointerDown(e: PointerEvent) {
    if (!engine) return;

    if (e.pointerType === 'pen') {
      if (stylusDeactivateTimer !== null) {
        clearTimeout(stylusDeactivateTimer);
        stylusDeactivateTimer = null;
      }
      stylusActive = true;
      if (e.buttons === 32) {
        previousTool = tool;
        tool = 'eraser';
        usingTemporaryTool = true;
      } else if (e.buttons === 2) {
        previousTool = tool;
        tool = 'cursor';
        usingTemporaryTool = true;
      }
    } else if (e.pointerType === 'touch' && stylusActive) {
      e.preventDefault();
      return;
    }
    
    if (gestureHandler.onPointerDown(e)) {
      if (gestureHandler.isGestureActive()) {
        engine.cancelStroke();
        if (renderState) renderState.activeOutline = null;
        markDirty(false);
      }
      return;
    }

    // Device change detection — load saved profile on pointer type change
    if (e.pointerType !== lastPointerType) {
      lastPointerType = e.pointerType;
      onDeviceChanged(e.pointerType);
    }

    if (tool === 'cursor') return;
    
    const pt = normalizePointerEvent(e, activeCanvas, engine.getViewport());
    
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    handlePointerDown(actionCtx, pt, e.ctrlKey || e.metaKey || e.shiftKey);
  }

  function onPointerMove(e: PointerEvent) {
    if (!engine) return;

    if (e.pointerType === 'touch' && stylusActive) {
      e.preventDefault();
      return;
    }
    
    const rect = baseCanvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio ?? 1;
    rawPointerScreen = {
      x: (e.clientX - rect.left) * dpr,
      y: (e.clientY - rect.top) * dpr,
    };
    if (renderState) renderState.rawPointerScreen = rawPointerScreen;
    
    if (gestureHandler.isGestureActive()) {
      const result = gestureHandler.onPointerMove(e, rect);
      if (result.type !== 'none') {
        currentViewport = result.newViewport!;
        markDirty(true);
        if (bgCtx) renderBackground(bgConfig, currentViewport);
      }
      return;
    }
    
    gestureHandler.onPointerMove(e, rect);
    if (gestureHandler.shouldIgnore()) return;

    if (tool === 'cursor') {
      if ((e.buttons & 1) || (e.buttons & 2)) {
          isPanning = true;
          engine.pan(e.movementX, e.movementY);
          currentViewport = engine.getViewport();
          markDirty(true);
          if (bgCtx) renderBackground(bgConfig, currentViewport);
      } else {
          isPanning = false;
      }
      return;
    }

    isPanning = false;
    const coalesced = getCoalescedPoints(e, activeCanvas, engine.getViewport());
    const pt = normalizePointerEvent(e, activeCanvas, engine.getViewport());
    handlePointerMove(actionCtx, pt, coalesced, e.buttons);
  }

  function onPointerUp(e: PointerEvent) {
    if (!engine) return;

    if (usingTemporaryTool && previousTool !== null) {
      tool = previousTool as Tool;
      previousTool = null;
      usingTemporaryTool = false;
    }

    if (e.pointerType === 'pen') {
      stylusDeactivateTimer = setTimeout(() => {
        stylusActive = false;
        stylusDeactivateTimer = null;
      }, PALM_REJECT_TIMEOUT);
    }

    const wasGesture = gestureHandler.isGestureActive();
    gestureHandler.onPointerUp(e);
    
    isPanning = false;

    if (!gestureHandler.shouldIgnore() && !wasGesture && tool !== 'cursor') {
        const pt = normalizePointerEvent(e, activeCanvas, engine.getViewport());
        handlePointerUp(actionCtx, pt);
    }
  }
  
  function onPointerLeave(e: PointerEvent) {
    if (!engine) return;
    gestureHandler.onPointerUp(e);
    isPanning = false;

    if (renderState?.eraserPos) {
        renderState.eraserPos = null;
        markDirty(false);
    }
  }

  function onPointerCancel(e: PointerEvent) {
    engine?.cancelStroke();

    if (stylusDeactivateTimer !== null) {
        clearTimeout(stylusDeactivateTimer);
        stylusDeactivateTimer = null;
    }
    stylusActive = false;

    if (usingTemporaryTool && previousTool !== null) {
        tool = previousTool as Tool;
        previousTool = null;
        usingTemporaryTool = false;
    }
    usingTemporaryTool = false;

    actionCtx.syncState();
    markDirty(true);
  }

  function onDoubleClick(e: MouseEvent) {
    if (!engine || !renderState || tool !== 'select') return;
    const pt = normalizePointerEvent(e as any, activeCanvas, currentViewport);

    const hitId = engine.hitTestTextPoint(pt.x, pt.y);
    if (hitId >= 0) {
      tool = 'text';
      
      // CRITICAL: Preemptively sync renderState to prevent Svelte's reactive 
      // handleToolChange block from executing its destructive teardown logic
      // which would otherwise clear the selection and auto-delete the empty editor!
      renderState.activeTool = 'text';

      engine.setTool('text');
      
      engine.setSelection([hitId]);
      actionCtx.syncState();
      textHandler.beginEdit(hitId, currentViewport);
      textFontSize = Math.round(textHandler.getState().fontSize / currentViewport[2]);
      
      actionCtx.syncState();
      markDirty(true);
    }
  }

  import type { CanvasAction } from './types';

  export function doAction(action: string | CustomEvent<CanvasAction>) {
    if (!engine) return;
    const payload = action instanceof CustomEvent ? action.detail : action;
    
    if (typeof payload === 'string') {
      if (payload.startsWith('tool:')) {
        const parts = payload.split(':');
        if (parts.length > 1) {
          tool = parts[1] as Tool;
        }
        return;
      }
    } else {
      if (payload.type === 'tool') {
        tool = payload.tool;
        return;
      }
    }
    dispatchAction(actionCtx, payload);
  }

  export function serialize(): string {
    if (!engine) return '';
    try {
      const data = JSON.parse(engine.serialize());
      data.background = bgConfig;
      return JSON.stringify(data);
    } catch {
      return '';
    }
  }

  /** Expose the base canvas element for thumbnail generation. */
  export function getBaseCanvas(): HTMLCanvasElement | undefined {
    return baseCanvas;
  }

  export function deserialize(json: string): boolean {
    if (!engine) return false;
    try {
      const data = JSON.parse(json);
      if (data.background) {
        bgConfig = data.background;
      } else {
        bgConfig = { type: 'none', color: '#d0d0d0', spacing: 20 };
      }
    } catch {}

    if (engine.deserialize(json)) {
      updateHistoryState();
      markDirty(true);
      preloadImageResources();
      if (bgCtx) renderBackground(bgConfig, currentViewport);
      console.log(`[Canvas] initial render complete. stroke count from engine: ${(engine as any)?.getStrokeCount?.() ?? 'unknown'}`);
      return true;
    }
    return false;
  }

  export function loadPage(json: string): boolean {
    if (!engine) return false;
    try {
      const data = JSON.parse(json);
      if (data.background) {
        bgConfig = data.background;
      } else {
        bgConfig = { type: 'none', color: '#d0d0d0', spacing: 20 };
      }
    } catch {}

    if (engine.loadPage(json)) {
      updateHistoryState();
      markDirty(true);
      preloadImageResources();
      if (bgCtx) renderBackground(bgConfig, currentViewport);
      return true;
    }
    return false;
  }

  export function serializePage(): string {
    if (!engine) return '';
    try {
      const data = JSON.parse(engine.serializePage());
      data.background = bgConfig;
      return JSON.stringify(data);
    } catch {
      return '';
    }
  }

  export function setCurrentPageId(id: string): void {
    if (engine) engine.setCurrentPageId(id);
  }

  export function stashHistory(): void {
    if (engine) engine.stashHistory();
  }

  /** Clear all engine state: objects, history, selection. No JSON parsing overhead. */
  export function clearEngine(): void {
    if (engine) {
      engine.clear();
      bgConfig = { type: 'none', color: 'transparent', spacing: 20 };
      updateHistoryState();
      markDirty(true);
      if (bgCtx) renderBackground(bgConfig, currentViewport);
    }
  }

  export function resetViewport(): void {
    if (engine) {
      engine.resetViewport();
      currentViewport = engine.getViewport();
      markDirty(true);
      if (bgCtx) renderBackground(bgConfig, currentViewport);
    }
  }

  export async function generateThumbnail(): Promise<string> {
    if (!baseCanvas) return '';
    forceRender();
    
    // Use the actual high-res pixel dimensions of the canvas
    const srcW = baseCanvas.width;
    const srcH = baseCanvas.height;
    if (srcW === 0 || srcH === 0) return '';
    
    const offscreen = document.createElement('canvas');
    offscreen.width = srcW;
    offscreen.height = srcH;
    const ctx = offscreen.getContext('2d');
    if (!ctx) return '';
    
    // Fill with a solid background so black strokes are visible even in dark mode
    if (bgConfig && bgConfig.type !== 'none' && bgConfig.color !== 'transparent') {
        ctx.fillStyle = bgConfig.color;
    } else {
        ctx.fillStyle = '#ffffff'; // Fallback to white for thumbnails
    }
    ctx.fillRect(0, 0, srcW, srcH);
    
    // Draw the actual canvas strokes on top
    ctx.drawImage(baseCanvas, 0, 0);
    
    // Export pristine PNG (avoid heavy jpeg artifacts by using PNG or high-quality WebP)
    return offscreen.toDataURL('image/png');
  }

  export function getCanUndo(): boolean {
    return engine ? engine.canUndo() : false;
  }

  export function getCanRedo(): boolean {
    return engine ? engine.canRedo() : false;
  }

  async function preloadImageResources() {
    if (!engine || !renderState) return;
    const objects = engine.getAllObjects();
    for (const obj of objects) {
      if (obj.object_type === 'image') {
        const imgObj = obj as ImageObjectData;
        if (renderState.imageCache.has(imgObj.resource_id)) continue;
        try {
          const result = await getResourceBytes(imgObj.resource_id, canvasFilePath ?? undefined);
          const blob = new Blob([new Uint8Array(result.data)]);
          const url = URL.createObjectURL(blob);
          const imgEl = new Image();
          imgEl.src = url;
          await new Promise((resolve, reject) => {
            imgEl.onload = resolve;
            imgEl.onerror = reject;
          });
          renderState.imageCache.set(imgObj.resource_id, imgEl);
        } catch (e) {
          console.warn('Failed to preload image resource', imgObj.resource_id, e);
        }
      }
    }
    markDirty(true);
  }

  let toastMessage: string | null = null;
  let toastTimeout: ReturnType<typeof setTimeout> | null = null;

  function showToast(msg: string, durationMs = 3000) {
    toastMessage = msg;
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => { toastMessage = null; }, durationMs);
  }

  async function importImageFile(file: File | Blob, dropX: number, dropY: number, filename?: string) {
    if (!engine || !renderState) return;
    if (!canvasFilePath) {
      showToast('Please save your canvas before importing images.');
      return;
    }
    const arrayBuffer = await file.arrayBuffer();
    const imageData = Array.from(new Uint8Array(arrayBuffer));
    const name = filename || (file instanceof File ? file.name : 'pasted-image.png');

    // Store the file via Python IPC
    const result = await importCanvasImage(imageData, name, canvasFilePath ?? undefined);

    // Get natural dimensions via browser Image
    const blob = new Blob([new Uint8Array(imageData)]);
    const url = URL.createObjectURL(blob);
    const imgEl = new Image();
    imgEl.src = url;
    await new Promise((resolve, reject) => {
      imgEl.onload = resolve;
      imgEl.onerror = reject;
    });
    const origW = imgEl.naturalWidth;
    const origH = imgEl.naturalHeight;

    // Cache for rendering
    renderState.imageCache.set(result.resource_id, imgEl);

    // Place image on canvas, max 400 canvas-units wide
    const scale = currentViewport[2];
    const maxW = 400 / scale;
    const aspectRatio = origH / origW;
    const w = Math.min(maxW, origW);
    const h = w * aspectRatio;

    engine.addImageObject(
      result.resource_id,
      dropX - w / 2,
      dropY - h / 2,
      w, h,
      origW, origH
    );

    updateHistoryState();
    markDirty(true);
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    if (!engine) return;
    const files = Array.from(e.dataTransfer?.files ?? []);
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) return;

    const rect = activeCanvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const vp = engine.getViewport();
    const canvasX = (screenX - vp[0]) / vp[2];
    const canvasY = (screenY - vp[1]) / vp[2];

    for (const file of imageFiles) {
      await importImageFile(file, canvasX, canvasY);
    }
  }

  function onPaste(e: ClipboardEvent) {
    if (!engine || !renderState) return;
    // Don't intercept paste when editing text
    if (textOverlayState && textOverlayState.editingTextId !== null) return;

    const items = Array.from(e.clipboardData?.items ?? []);
    const imageItem = items.find(item => item.type.startsWith('image/'));
    if (!imageItem) return;

    e.preventDefault();
    const file = imageItem.getAsFile();
    if (!file) return;

    // Place at center of current viewport
    const rect = activeCanvas.getBoundingClientRect();
    const vp = engine.getViewport();
    const centerScreenX = rect.width / 2;
    const centerScreenY = rect.height / 2;
    const canvasX = (centerScreenX - vp[0]) / vp[2];
    const canvasY = (centerScreenY - vp[1]) / vp[2];

    importImageFile(file, canvasX, canvasY);
  }

  export function exportSvg(width: number, height: number): string {
    // Note for Phase 9: Background is implemented purely in Svelte, 
    // so Rust's engine.exportSvg natively ignores it.
    return engine ? engine.exportSvg(width, height) : '';
  }

  function onWheel(e: WheelEvent) {
    if (!engine || !renderState) return;
    currentViewport = gestureHandler.onWheel(e, baseCanvas.getBoundingClientRect());
    markDirty(true);
    if (bgCtx) renderBackground(bgConfig, currentViewport);

    // Sync text editor overlay with the new viewport immediately during scroll
    if (textOverlayState && textOverlayState.editingTextId !== null) {
      textHandler.beginEdit(textOverlayState.editingTextId, currentViewport);
      syncTextOverlay();
    }
  }

  $: cursorStyle = getCursorForTool(tool, isPanning, selectionState?.mode ?? 'idle', selectionState?.activeHandle ?? -1, hoverCursor);

  $: if (bgCtx && bgConfig) {
    renderBackground(bgConfig, currentViewport);
  }

  // Re-render background whenever individual config fields change (e.g. spacing slider).
  // The block above only fires on reference changes; this one fires on property mutations.
  $: bgConfig && bgCtx && void [bgConfig.spacing, bgConfig.type, bgConfig.color] && renderBackground(bgConfig, currentViewport);

  export function updateBackground(newConfig: BackgroundConfig) {
    bgConfig = newConfig; // Svelte binding changes this, and the reactive block above catches it
  }

  function renderBackground(config: BackgroundConfig, viewport: [number, number, number]) {
    if (!bgCtx || !bgCanvas) return;
    const w = bgCanvas.width;
    const h = bgCanvas.height;
    
    if (w === 0 || h === 0) return;
    
    // Clear the context before re-filling
    bgCtx.clearRect(0, 0, w, h);
    
    // Fill the background layer with the original baseline canvas color
    // so dark mode doesn't shine a black void through the canvases!
    bgCtx.fillStyle = RENDER.CANVAS_BACKGROUND;
    bgCtx.fillRect(0, 0, w, h);

    if (config.type === "none") return;

    const scale = viewport[2];
    if (config.spacing * scale < 4) return;

    const tx = viewport[0];
    const ty = viewport[1];

    const startX = (0 - tx) / scale;
    const startY = (0 - ty) / scale;
    const endX = (w - tx) / scale;
    const endY = (h - ty) / scale;

    const snapX = Math.floor(startX / config.spacing) * config.spacing;
    const snapY = Math.floor(startY / config.spacing) * config.spacing;

    bgCtx.save();
    bgCtx.fillStyle = config.color;
    bgCtx.strokeStyle = config.color;

    // Convert canvas-space point to screen-space
    const c2sX = (cx: number) => cx * scale + tx;
    const c2sY = (cy: number) => cy * scale + ty;

    bgCtx.beginPath();

    if (config.type === "dots") {
      const radius = Math.max(0.5, 1.0 * scale);
      for (let x = snapX; x <= endX; x += config.spacing) {
        for (let y = snapY; y <= endY; y += config.spacing) {
          const sx = c2sX(x);
          const sy = c2sY(y);
          bgCtx.moveTo(sx + radius, sy);
          bgCtx.arc(sx, sy, radius, 0, Math.PI * 2);
        }
      }
      bgCtx.fill();
    } else if (config.type === "dotted") {
      const radius = Math.max(0.3, 0.6 * scale);
      const effectiveSpacing = config.spacing * 0.5;
      const snapXDot = Math.floor(startX / effectiveSpacing) * effectiveSpacing;
      const snapYDot = Math.floor(startY / effectiveSpacing) * effectiveSpacing;
      for (let x = snapXDot; x <= endX; x += effectiveSpacing) {
        for (let y = snapYDot; y <= endY; y += effectiveSpacing) {
          const sx = c2sX(x);
          const sy = c2sY(y);
          bgCtx.moveTo(sx + radius, sy);
          bgCtx.arc(sx, sy, radius, 0, Math.PI * 2);
        }
      }
      bgCtx.fill();
    } else if (config.type === "grid") {
      bgCtx.lineWidth = 1;
      for (let x = snapX; x <= endX; x += config.spacing) {
        bgCtx.moveTo(c2sX(x), 0);
        bgCtx.lineTo(c2sX(x), h);
      }
      for (let y = snapY; y <= endY; y += config.spacing) {
        bgCtx.moveTo(0, c2sY(y));
        bgCtx.lineTo(w, c2sY(y));
      }
      bgCtx.stroke();
    } else if (config.type === "lines" || config.type === "ruled" || config.type === "cornell") {
      bgCtx.lineWidth = 1;
      for (let y = snapY; y <= endY; y += config.spacing) {
        bgCtx.moveTo(0, c2sY(y));
        bgCtx.lineTo(w, c2sY(y));
      }
      bgCtx.stroke();

      if (config.type === "ruled" || config.type === "cornell") {
        bgCtx.beginPath();
        bgCtx.lineWidth = 2;
        bgCtx.strokeStyle = "rgba(255, 170, 170, 0.6)";
        if (config.type === "ruled") {
           // margin line at spacing * 3 from origin
           const mx = c2sX(config.spacing * 3);
           bgCtx.moveTo(mx, 0);
           bgCtx.lineTo(mx, h);
        } else {
           // roughly 30% from the left of the viewport? "in canvas-space" - prompt says:
           // "roughly 30% from the left in canvas-space. Wait, paper width isn't well defined."
           // Let's rule it at a fixed canvas-space x position, e.g. 200 or 300? 
           // Prompt says: "roughly 30% from the left in canvas-space. The vertical line color..."
           // Let's use startX + (endX - startX)*0.3? No, that drifts with panning!
           // "in canvas-space" means a fixed coordinate. 30% of a typical 800px width? Let's use 240.
           const mx = c2sX(240);
           bgCtx.moveTo(mx, 0);
           bgCtx.lineTo(mx, h);
        }
        bgCtx.stroke();
      }
    } else if (config.type === "isometric") {
      bgCtx.lineWidth = 1;
      bgCtx.strokeStyle = config.color;
      bgCtx.globalAlpha = 0.7;
      const hSpace = config.spacing * Math.sqrt(3);

      const snapXIso = Math.floor(startX / hSpace) * hSpace - hSpace;
      const snapYIso = Math.floor(startY / config.spacing) * config.spacing - config.spacing;

      for (let y = snapYIso; y <= endY + config.spacing; y += config.spacing) {
        bgCtx.moveTo(0, c2sY(y));
        bgCtx.lineTo(w, c2sY(y));
      }
      
      const diagW = Math.max(w, h) / scale * 2;
      const dx = Math.cos(Math.PI/6) * diagW;
      const dy = Math.sin(Math.PI/6) * diagW;

      for (let x = snapXIso - diagW; x <= endX + diagW; x += config.spacing) {
        bgCtx.moveTo(c2sX(x), c2sY(startY - diagW));
        bgCtx.lineTo(c2sX(x + dx), c2sY(startY - diagW + dy));
        
        bgCtx.moveTo(c2sX(x), c2sY(endY + diagW));
        bgCtx.lineTo(c2sX(x + dx), c2sY(endY + diagW - dy));
      }
      bgCtx.stroke();
    } else if (config.type === "music_staff") {
      bgCtx.lineWidth = 1;
      const groupSpacing = config.spacing * 4;
      const lineSpacing = config.spacing * 0.6;
      const snapYGroup = Math.floor(startY / groupSpacing) * groupSpacing;

      for (let y = snapYGroup; y <= endY; y += groupSpacing) {
        for (let i = 0; i < 5; i++) {
          const ly = y + i * lineSpacing;
          if (ly >= startY && ly <= endY) {
            bgCtx.moveTo(0, c2sY(ly));
            bgCtx.lineTo(w, c2sY(ly));
          }
        }
      }
      bgCtx.stroke();
    }

    bgCtx.restore();
  }

  let shapeToast: { message: string, shapeJson: string, strokeId: number, timer: ReturnType<typeof setTimeout> } | null = null;

  function showShapeToast(shapeJson: string, strokeId: number) {
    if (shapeToast) clearTimeout(shapeToast.timer);
    
    let shapeName = "Shape";
    try {
      const shape = JSON.parse(shapeJson);
      if (shape.Line) shapeName = "Line";
      else if (shape.Rectangle) shapeName = "Rectangle";
      else if (shape.Circle) shapeName = "Circle";
      else if (shape.Triangle) shapeName = "Triangle";
      else if (shape.Arrow) shapeName = "Arrow";
    } catch (e) {}

    shapeToast = {
      message: `${shapeName} detected — Replace?`,
      shapeJson,
      strokeId,
      timer: setTimeout(() => { shapeToast = null; }, 3000)
    };
  }

  function handleShapeReplace() {
    if (!shapeToast) return;
    engine.replaceStrokeWithShape(shapeToast.strokeId, shapeToast.shapeJson);
    clearTimeout(shapeToast.timer);
    shapeToast = null;
    updateHistoryState();
    markDirty(true);
  }

  function handleShapeKeep() {
    if (!shapeToast) return;
    clearTimeout(shapeToast.timer);
    shapeToast = null;
  }
</script>

<svelte:window on:resize={setupDPR} on:paste={onPaste} />

<div class="canvas-container">
  <canvas bind:this={bgCanvas} class="canvas-layer" style="pointer-events: none;"></canvas>
  <canvas bind:this={baseCanvas} class="canvas-layer base-layer" style="pointer-events: none;"></canvas>
  <canvas
    bind:this={activeCanvas}
    class="canvas-layer active-layer"
    style="touch-action: none; cursor: {cursorStyle};"
    on:pointerdown={onPointerDown}
    on:pointermove={onPointerMove}
    on:pointerup={onPointerUp}
    on:pointercancel={onPointerCancel}
    on:pointerleave={onPointerLeave}
    on:dblclick={onDoubleClick}
    on:wheel|nonpassive={onWheel}
    on:dragover={onDragOver}
    on:drop={onDrop}
  ></canvas>
  {#if textOverlayState && textOverlayState.editingTextId !== null}
    <div
      class="text-overlay-container"
      style="position:absolute; left:{textOverlayState.overlayX}px; top:{textOverlayState.overlayY}px;
             width:max-content; min-width:{textOverlayState.overlayW}px;
             transform:rotate({textOverlayState.rotation ?? 0}rad);
             transform-origin:top left; z-index:10; pointer-events:none;"
    >
      <div
        contenteditable="true"
        role="textbox"
        tabindex="0"
        use:attachTextEditor
        style="font-family:{textOverlayState.fontFamily}; font-size:{textOverlayState.fontSize}px;
               color:{textOverlayState.color}; font-weight:{textOverlayState.bold ? 'bold' : 'normal'};
               font-style:{textOverlayState.italic ? 'italic' : 'normal'};
               min-width:100px; padding:0; outline:none;
               margin:0; border:none; line-height:{RENDER.TEXT_LINE_HEIGHT};
               white-space:pre-wrap;
               background:transparent; caret-color:{textOverlayState.color};
               pointer-events:auto;"
        on:input={(e) => { 
          if (textHandler.onInput(e)) {
            actionCtx.syncState();
            markDirty(true);
          }
        }}
        on:blur={(e) => { textHandler.onBlur(e.relatedTarget); syncTextOverlay(); updateHistoryState(); }}
        on:keydown={(e) => { if (textHandler.onKeydown(e)) { syncTextOverlay(); markDirty(true); } }}
      ></div>
    </div>
  {/if}
  {#if toastMessage}
    <div class="image-toast">{toastMessage}</div>
  {/if}
  {#if shapeToast}
    <div class="shape-toast">
      <span class="message">{shapeToast.message}</span>
      <div class="actions">
        <button on:click={handleShapeKeep} class="keep-btn">Keep</button>
        <button on:click={handleShapeReplace} class="replace-btn">Replace</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .canvas-container {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }
  .canvas-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: block;
  }
  .active-layer {
    pointer-events: auto;
  }
  .image-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: #333;
    color: #fff;
    padding: 10px 24px;
    border-radius: 8px;
    font-size: 14px;
    z-index: 100;
    pointer-events: none;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
  }
  .shape-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: #2a2a2a;
    color: #fff;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  }
  .shape-toast .actions {
    display: flex;
    gap: 8px;
  }
  .shape-toast button {
    padding: 6px 12px;
    border-radius: 4px;
    border: none;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .shape-toast .keep-btn {
    background: #444;
    color: #fff;
  }
  .shape-toast .keep-btn:hover {
    background: #555;
  }
  .shape-toast .replace-btn {
    background: #2563eb;
    color: #fff;
  }
  .shape-toast .replace-btn:hover {
    background: #1d4ed8;
  }
</style>
