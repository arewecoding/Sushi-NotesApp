import type { DrawingEngine } from './engine';
import type { Tool } from './types';
import type { SelectionHandler } from './tools/SelectionHandler';
import type { TextEditorHandler } from './tools/TextEditorHandler';
import { getStrokeConfig, saveStrokeConfig } from './client/canvas';

type Viewport = [number, number, number];

export interface ActionContext {
  engine: DrawingEngine;
  viewport: Viewport;
  activeTool: Tool;
  selectionHandler: SelectionHandler;
  textHandler: TextEditorHandler;
  activeTextStyle: { fontFamily: string; fontSize: number; fontWeight: number; fontStyle: string; color: string };
  updateTextStyle: (style: Partial<ActionContext['activeTextStyle']>) => void;
  getSize: () => number;
  requestRedraw: (baseLayer?: boolean) => void;
  updateHistory: () => void;
  syncState: () => void;
  updateTextSize: (size: number) => void;
  setHoverCursor: (cursor: string) => void;
  setEraserPos: (pos: {x: number; y: number; radius: number} | null) => void;
  setActiveOutline: (outline: Float64Array | null) => void;
  setShiftHeld: (held: boolean) => void;
  onShapeDetected?: (shapeJson: string, strokeId: number) => void;
}

export interface InteractivePointer {
  x: number;
  y: number;
  pressure: number;
  timestamp: number;
  shiftKey?: boolean;
}

function getBindings(ctx: ActionContext) {
    return {
       tool: ctx.activeTool,
       engine: ctx.engine,
       selectionHandler: ctx.selectionHandler,
       textHandler: ctx.textHandler,
       syncState: ctx.syncState,
       requestRedraw: ctx.requestRedraw,
       activeTextStyle: ctx.activeTextStyle,
       updateTextStyle: ctx.updateTextStyle,
       updateTextSize: ctx.updateTextSize,
       updateHistory: ctx.updateHistory,
       setActiveOutline: ctx.setActiveOutline,
       setEraserPos: ctx.setEraserPos,
       setHoverCursor: ctx.setHoverCursor,
       setShiftHeld: ctx.setShiftHeld,
       onShapeDetected: ctx.onShapeDetected
    };
}

let pendingShapeTimer: ReturnType<typeof setTimeout> | null = null;

export function eraseAt(ctx: ActionContext, pt: InteractivePointer, size: number) {
    const { engine, viewport, requestRedraw, updateHistory, setEraserPos } = ctx;
    const effectiveSize = Math.max(size * 3, 12);
    const radius = effectiveSize / viewport[2];
    setEraserPos({ x: pt.x, y: pt.y, radius });
    
    // Hit-test strokes and text objects for erasure
    const hitIds = engine.getStrokesAt(pt.x, pt.y, radius);
    const textHit = engine.hitTestTextPoint(pt.x, pt.y);
    if (textHit >= 0) hitIds.push(textHit);
    
    if (hitIds.length > 0) {
      engine.commitErase(hitIds);
      updateHistory();
    }
    requestRedraw();
}

export function handlePointerDown(
  ctx: ActionContext,
  pt: InteractivePointer,
  isMulti: boolean
): void {
  const { activeTool: tool, engine, selectionHandler, textHandler, syncState, requestRedraw, activeTextStyle, updateTextSize, updateHistory } = ctx;

  if (tool === 'text') {
    const editingId = textHandler.getState().editingTextId;

    // If editing: check for handle hits (resize/rotate) before committing
    if (editingId !== null && engine.hasSelection()) {
      const handled = selectionHandler.onPointerDown(pt.x, pt.y, ctx.viewport, false);
      if (handled) {
        const mode = selectionHandler.getState().mode;
        if (mode === 'resizing' || mode === 'rotating' || mode === 'dragging') {
          // User clicked a selection handle or bounding box edge — delegate to selection handler
          textHandler.preventBlur();
          syncState();
          requestRedraw();
          return;
        }
        // Not a handle click (drag/marquee) — reset and proceed with text logic
        selectionHandler.reset();
      }
    }

    if (editingId !== null) {
      if (textHandler.commit()) updateHistory();
      syncState();
      requestRedraw(true);
      return;
    }

    const hitId = engine.hitTestTextPoint(pt.x, pt.y);
    if (hitId >= 0) {
      engine.setSelection([hitId]);
      syncState();
      textHandler.beginEdit(hitId, ctx.viewport);
      updateTextSize(Math.round(textHandler.getState().fontSize / ctx.viewport[2]));
    } else {
      const styleStr = JSON.stringify({
        font_family: activeTextStyle.fontFamily,
        font_size: activeTextStyle.fontSize,
        font_weight: activeTextStyle.fontWeight,
        font_style: activeTextStyle.fontStyle,
        color: activeTextStyle.color,
      });
      textHandler.beginNew(pt.x, pt.y, ctx.viewport, styleStr);
      syncState();
      updateHistory();
      updateTextSize(activeTextStyle.fontSize);
    }
    syncState();
    requestRedraw(true);
    return;
  }

  if (tool === 'select') {
    if (selectionHandler.onPointerDown(pt.x, pt.y, ctx.viewport, isMulti)) {
      syncState();
      requestRedraw();
    }
  } else if (tool === 'eraser') {
    eraseAt(ctx, pt, ctx.getSize());
  } else {
    if (pendingShapeTimer !== null) {
      clearTimeout(pendingShapeTimer);
      pendingShapeTimer = null;
    }
    engine.beginStroke(pt.x, pt.y, pt.pressure, pt.timestamp);
    requestRedraw();
  }
}

export function handlePointerMove(
  ctx: ActionContext,
  pt: InteractivePointer,
  coalesced: InteractivePointer[],
  buttons: number
): void {
  const { activeTool: tool, engine, selectionHandler, syncState, requestRedraw, setActiveOutline, setHoverCursor, setEraserPos } = ctx;
  const size = ctx.getSize();
  const effectiveSize = Math.max(size * 3, 12);

  if (!(buttons & 1) && !(buttons & 32)) {
    if (tool === 'eraser') {
      const radius = effectiveSize / ctx.viewport[2];
      setEraserPos({ x: pt.x, y: pt.y, radius });
      requestRedraw();
    }
    if (tool === 'select' || (tool === 'text' && engine.hasSelection())) {
      if (selectionHandler.onPointerMove(pt.x, pt.y, ctx.viewport, true, pt.shiftKey)) {
        setHoverCursor(selectionHandler.getState().hoverCursor);
      }
    }
    return;
  }

  // Active drags
  if (tool === 'select') {
    if (selectionHandler.onPointerMove(pt.x, pt.y, ctx.viewport, false, pt.shiftKey)) {
      syncState();
    }
    return;
  }

  if (tool === 'eraser') {
    eraseAt(ctx, pt, size);
    return;
  }

  if (tool === 'text') {
    if (selectionHandler.getState().mode !== 'idle') {
      if (buttons & 1) {
        if (selectionHandler.onPointerMove(pt.x, pt.y, ctx.viewport, false, pt.shiftKey)) {
          syncState();
          requestRedraw();
        }
      }
      return;
    }
    return;
  }

  // Drawing
  let outline: Float64Array | null = null;
  for (const c of coalesced) {
    outline = engine.continueStroke(c.x, c.y, c.pressure, c.timestamp, !!c.shiftKey);
  }
  setActiveOutline(outline);
  if (ctx.setShiftHeld) ctx.setShiftHeld(!!pt.shiftKey);
  requestRedraw();
}

export function handlePointerUp(
  ctx: ActionContext,
  pt: InteractivePointer
): void {
  const { activeTool: tool, engine, selectionHandler, syncState, requestRedraw, updateHistory, updateTextSize, setActiveOutline } = ctx;

  if (tool === 'select') {
    if (selectionHandler.onPointerUp(pt.x, pt.y, ctx.viewport)) {
        const selectedIds = engine.getSelectedIds();
        for (const id of selectedIds) {
          try {
            const objStr = engine.getTextObject(id);
            const obj = JSON.parse(objStr);
            if (obj && obj.font_size) {
              ctx.updateTextStyle({
                fontFamily: obj.font_family,
                fontSize: Math.round(obj.font_size),
                fontWeight: obj.font_weight > 400 || obj.font_weight === 'bold' ? 700 : 400,
                fontStyle: obj.font_style === 'italic' ? 'italic' : 'normal',
                color: obj.color
              });
              break;
            }
          } catch (_) {}
        }
        syncState(); 
        requestRedraw(true);
        updateHistory();
    }
    syncState();
    requestRedraw();
    return;
  }
  
  if (tool === 'eraser') return;

  if (tool === 'text') {
    // Handle completion of selection operations (resize/rotate) during text editing
    if (selectionHandler.getState().mode !== 'idle') {
      if (selectionHandler.onPointerUp(pt.x, pt.y, ctx.viewport)) {
        syncState();
        requestRedraw(true);
        updateHistory();
      }
      // Refresh the overlay to match the transformed object
      const editingId = ctx.textHandler.getState().editingTextId;
      if (editingId !== null) {
        ctx.textHandler.beginEdit(editingId, ctx.viewport);
        ctx.textHandler.resumeFocus();
        syncState();
      }
    }
    return;
  }

  if (ctx.setShiftHeld) ctx.setShiftHeld(false);
  const strokeId = engine.endStroke();
  setActiveOutline(null);
  syncState();
  requestRedraw(true);
  updateHistory();

  // Schedule shape recognition if handler is provided
  if (ctx.onShapeDetected && strokeId >= 0) {
    pendingShapeTimer = setTimeout(() => {
      pendingShapeTimer = null;
      const recognized = engine.checkForShape(strokeId);
      console.log("shape check fired, result:", recognized, "strokeId:", strokeId);
      if (recognized && ctx.onShapeDetected) {
        ctx.onShapeDetected(JSON.stringify(recognized), strokeId);
      }
    }, 800);
  }
}

function getResizeCursor(idx: number) {
  if (idx === 0 || idx === 4) return 'nwse-resize';
  if (idx === 2 || idx === 6) return 'nesw-resize';
  if (idx === 1 || idx === 5) return 'ns-resize';
  if (idx === 3 || idx === 7) return 'ew-resize';
  return 'default';
}

const ROTATE_CURSOR = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M21.5 2v6h-6' stroke='%23000' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M21.5 8A9 9 0 1 0 18.36 18.36' stroke='%23000' stroke-width='3.5' stroke-linecap='round'/%3E%3Cpath d='M21.5 2v6h-6' stroke='%23fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M21.5 8A9 9 0 1 0 18.36 18.36' stroke='%23fff' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E") 12 12, pointer`;

export function getCursorForTool(
    tool: Tool, 
    isPanning: boolean, 
    selectionMode: string, 
    activeHandle: number, 
    hoverCursor: string
): string {
    if (tool === 'cursor') return isPanning ? 'grabbing' : 'grab';
    if (tool === 'eraser') return 'none';
    if (tool === 'select') {
       if (selectionMode === 'dragging') return 'grabbing';
       if (selectionMode === 'rotating' || hoverCursor === 'rotate') return ROTATE_CURSOR;
       if (selectionMode === 'resizing') return getResizeCursor(activeHandle);
       return hoverCursor;
    }
    if (tool === 'text') {
       if (selectionMode === 'dragging') return 'grabbing';
       if (selectionMode === 'rotating' || hoverCursor === 'rotate') return ROTATE_CURSOR;
       if (selectionMode === 'resizing') return getResizeCursor(activeHandle);
       if (hoverCursor !== 'default') return hoverCursor;
       return 'text';
    }
    return 'crosshair';
}

export async function handleDeviceChanged(ctx: ActionContext, pointerType: string) {
    try {
      const result = await getStrokeConfig(pointerType);
      if (result.config) {
        ctx.engine.setToolConfigs(JSON.stringify(result.config));
        await saveStrokeConfig(pointerType, result.config);
      }
    } catch (e) {
      // Ignore
    }
}

export interface ActionStateParams {
   tool: Tool;
   color: string;
   size: number;
   renderState: any; 
}

export function handleToolChange(ctx: ActionContext, params: ActionStateParams) {
    const { tool, color, size, renderState } = params;
    const { engine, textHandler, syncState, requestRedraw, updateHistory } = getBindings(ctx);
    
    if (renderState && renderState.activeTool === 'select' && tool !== 'select') {
      engine.clearSelection();
      syncState(); 
    }
    
    if (renderState && renderState.activeTool !== tool) {
      if (textHandler.getState().editingTextId !== null) {
        if (textHandler.commit()) updateHistory();
      }
      engine.setSelectedTextId(-1);
      syncState();
      requestRedraw(true);
    }
    
    engine.setTool(tool);
    engine.setColor(color);
    engine.setSize(size);
    
    if (renderState) {
        renderState.activeTool = tool;
        renderState.activeColor = color;
        renderState.activeOpacity = tool === 'highlighter' ? 0.5 : 1.0;
        renderState.eraserRadius = size;
    }
}

let preDragColorState: string | null = null;

import type { CanvasAction } from './types';

export function dispatchAction(ctx: ActionContext, action: string | CanvasAction) {
    const { tool, engine, selectionHandler, textHandler, currentViewport: viewport, activeTextStyle, updateTextStyle, syncState, updateHistory, requestRedraw } = { currentViewport: ctx.viewport, ...getBindings(ctx) };
    
    if (typeof action === 'object') {
       if (action.type === 'undo' && engine.undo()) {
         updateHistory();
       } else if (action.type === 'redo' && engine.redo()) {
         updateHistory();
       } else if (action.type === 'delete') {
         if (tool === 'select' && engine.getSelectedIds().length > 0) {
           engine.deleteSelected();
           updateHistory();
           syncState();
           requestRedraw(true);
         }
       } else if (action.type === 'clear') {
         if (tool === 'select') {
           engine.clearSelection();
           syncState();
         }
       } else if (action.type === 'duplicate') {
         if (tool === 'select' && engine.getSelectedIds().length > 0) {
           engine.duplicateSelected();
           updateHistory();
           syncState();
           requestRedraw(true);
         }
       } else if (action.type === 'nudge') {
         if (tool === 'select') {
           if (selectionHandler.onNudge(action.dx, action.dy)) {
             updateHistory();
             syncState();
             requestRedraw(true);
           }
         }
       }
       return;
    }

    if (action === 'undo' && engine.undo()) {
      updateHistory();
    } else if (action === 'redo' && engine.redo()) {
      updateHistory();
    } else if (action === 'select:delete') {
      if (tool === 'select' && engine.getSelectedIds().length > 0) {
        engine.deleteSelected();
        updateHistory();
        syncState();
        requestRedraw(true);
      }
    } else if (action === 'select:clear') {
      if (tool === 'select') {
        engine.clearSelection();
        syncState();
      }
    } else if (action === 'select:duplicate') {
       if (tool === 'select' && engine.getSelectedIds().length > 0) {
         engine.duplicateSelected();
         updateHistory();
         syncState();
         requestRedraw(true);
       }
    } else if (action.startsWith('select:nudge:')) {
       if (tool === 'select') {
         const parts = action.split(':');
         const dx = parseFloat(parts[2]);
         const dy = parseFloat(parts[3]);
         if (selectionHandler.onNudge(dx, dy)) {
           updateHistory();
           syncState();
           requestRedraw(true);
         }
       }
    } else if (action.startsWith('color:preview:')) {
      const parts = action.split(':');
      const previewColor = parts.slice(2).join(':');
      if (textHandler.getState().editingTextId !== null) {
        const id = textHandler.getState().editingTextId!;
        engine.updateTextStyle(id, JSON.stringify({ color: previewColor }));
        textHandler.beginEdit(id, viewport);
        syncState();
        requestRedraw(true);
      } else if (tool === 'select' && engine.getSelectedIds().length > 0) {
        if (!preDragColorState) preDragColorState = engine.getSelectedColorsJson();
        engine.setSelectedColorPreview(previewColor);
        syncState();
        requestRedraw(true);
      }
    } else if (action.startsWith('color:commit:')) {
      const parts = action.split(':');
      const commitColor = parts.slice(2).join(':');
      if (textHandler.getState().editingTextId !== null) {
        const id = textHandler.getState().editingTextId!;
        engine.updateTextStyle(id, JSON.stringify({ color: commitColor }));
        textHandler.beginEdit(id, viewport);
        syncState();
        requestRedraw(true);
      } else if (tool === 'select' && engine.getSelectedIds().length > 0) {
        if (!preDragColorState) preDragColorState = engine.getSelectedColorsJson();
        engine.commitColorChange(preDragColorState, commitColor);
        preDragColorState = null;
        updateHistory();
        syncState();
        requestRedraw(true);
      }
    } else if (action.startsWith('textstyle:')) {
      const styleJson = action.substring('textstyle:'.length);
      const parsed = JSON.parse(styleJson);
      updateTextStyle({
        fontFamily: parsed.font_family ?? activeTextStyle.fontFamily,
        fontSize: parsed.font_size ?? activeTextStyle.fontSize,
        fontWeight: parsed.font_weight ?? activeTextStyle.fontWeight,
        fontStyle: parsed.font_style ?? activeTextStyle.fontStyle,
        color: parsed.color ?? activeTextStyle.color,
      });
      if (textHandler.getState().editingTextId !== null) {
        const id = textHandler.getState().editingTextId!;
        engine.updateTextStyle(id, styleJson);
        textHandler.beginEdit(id, viewport);
        textHandler.resumeFocus();
        syncState();
        requestRedraw(true);
      }
    }
}
