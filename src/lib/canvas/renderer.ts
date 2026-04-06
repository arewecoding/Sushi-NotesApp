import type { Tool } from './types';
import type { StrokeData, TextObjectData, ImageObjectData, CanvasObjectData, RenderState } from './types';
import { RENDER, DEFAULTS } from './config';

// ─── RULE 1: Single source of truth for font strings ─────────────────────────
export function buildFontString(
  fontStyle: string,
  fontWeight: number,
  fontSize: number,
  fontFamily: string
): string {
  return `${fontStyle} ${fontWeight} ${fontSize}px ${fontFamily}`;
}

function renderBaseLayer(
  baseCtx: CanvasRenderingContext2D,
  state: RenderState,
  viewport?: [number, number, number]
): Array<{ id: number; w: number; h: number }> {
  const dpr = window.devicePixelRatio ?? 1;
  const boundsUpdates: Array<{ id: number; w: number; h: number }> = [];

  baseCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  baseCtx.clearRect(0, 0, baseCtx.canvas.width / dpr, baseCtx.canvas.height / dpr);

  if (viewport) {
    const [ox, oy, scale] = viewport;
    baseCtx.setTransform(dpr * scale, 0, 0, dpr * scale, ox * dpr, oy * dpr);
  }

  for (const obj of state.objects) {
    if (obj.object_type === 'stroke') {
      const stroke = obj as StrokeData;
      if (state.highlightedIds && state.highlightedIds.has(stroke.id)) continue;

      const isSelected = state.selectedIds && state.selectedIds.has(stroke.id);
      if (isSelected && state.liveTransform && state.selectionBounds) {
        baseCtx.save();
        const { x, y, w, h } = state.selectionBounds;
        const cx = x + w / 2;
        const cy = y + h / 2;
        baseCtx.translate(cx, cy);
        baseCtx.rotate(state.liveTransform.rotation);
        baseCtx.scale(state.liveTransform.scaleX, state.liveTransform.scaleY);
        baseCtx.translate(
          -cx + state.liveTransform.translateX,
          -cy + state.liveTransform.translateY
        );
        drawStroke(baseCtx, stroke);
        baseCtx.restore();
      } else {
        drawStroke(baseCtx, stroke);
      }
    } else if (obj.object_type === 'text') {
      const t = obj as TextObjectData;
      const isBeingEdited = state.editingTextId !== null && t.id === state.editingTextId;
      if (!isBeingEdited && !t.content) continue;

      const isSelected = state.selectedIds && state.selectedIds.has(t.id);

      // Even for edited text, we need to measure bounds for accurate selection box
      // Set up the font context for measurement
      baseCtx.save();
      baseCtx.font = buildFontString(
        t.font_style ?? DEFAULTS.FONT_STYLE,
        t.font_weight ?? DEFAULTS.FONT_WEIGHT,
        t.font_size,
        t.font_family ?? DEFAULTS.FONT_FAMILY
      );

      const lines = (t.content || '').split('\n');
      const lineHeight = t.font_size * RENDER.TEXT_LINE_HEIGHT;

      let maxLineWidth = 0;
      for (const line of lines) {
        const w = baseCtx.measureText(line || ' ').width;
        if (line !== '') {
          maxLineWidth = Math.max(maxLineWidth, w);
        }
      }
      baseCtx.restore();

      const worldH = t.font_size * RENDER.TEXT_LINE_HEIGHT * lines.length;
      if (maxLineWidth > 0) {
        boundsUpdates.push({ id: t.id, w: maxLineWidth, h: worldH });
      }

      // Skip visual rendering for the text being actively edited (overlay handles it)
      if (isBeingEdited) continue;

      if (isSelected && state.liveTransform && state.selectionBounds) {
        baseCtx.save();
        const { x, y, w, h } = state.selectionBounds;
        const scx = x + w / 2;
        const scy = y + h / 2;
        baseCtx.translate(scx, scy);
        baseCtx.rotate(state.liveTransform.rotation);
        baseCtx.scale(state.liveTransform.scaleX, state.liveTransform.scaleY);
        baseCtx.translate(
          -scx + state.liveTransform.translateX,
          -scy + state.liveTransform.translateY
        );
      }

      baseCtx.save();
      baseCtx.globalAlpha = t.opacity ?? 1.0;
      baseCtx.fillStyle = t.color ?? DEFAULTS.COLOR;
      baseCtx.font = buildFontString(
        t.font_style ?? DEFAULTS.FONT_STYLE,
        t.font_weight ?? DEFAULTS.FONT_WEIGHT,
        t.font_size,
        t.font_family ?? DEFAULTS.FONT_FAMILY
      );
      baseCtx.textBaseline = 'top';

      const halfLeading = (RENDER.TEXT_LINE_HEIGHT - 1.0) * t.font_size / 2;

      if (t.rotation !== 0) {
        baseCtx.translate(t.x, t.y);
        baseCtx.rotate(t.rotation);
        for (let i = 0; i < lines.length; i++) {
          if (lines[i] !== '') {
            baseCtx.fillText(lines[i], 0, halfLeading + i * lineHeight);
          }
        }
      } else {
        for (let i = 0; i < lines.length; i++) {
          if (lines[i] !== '') {
            baseCtx.fillText(lines[i], t.x, t.y + halfLeading + i * lineHeight);
          }
        }
      }

      baseCtx.restore();

      if (isSelected && state.liveTransform && state.selectionBounds) {
        baseCtx.restore();
      }


    } else if (obj.object_type === 'image') {
      const img = obj as ImageObjectData;
      const cachedImg = state.imageCache?.get(img.resource_id);
      if (!cachedImg) continue;

      const isSelected = state.selectedIds && state.selectedIds.has(img.id);

      if (isSelected && state.liveTransform && state.selectionBounds) {
        baseCtx.save();
        const { x, y, w, h } = state.selectionBounds;
        const scx = x + w / 2;
        const scy = y + h / 2;
        baseCtx.translate(scx, scy);
        baseCtx.rotate(state.liveTransform.rotation);
        baseCtx.scale(state.liveTransform.scaleX, state.liveTransform.scaleY);
        baseCtx.translate(
          -scx + state.liveTransform.translateX,
          -scy + state.liveTransform.translateY
        );
      }

      baseCtx.save();
      baseCtx.globalAlpha = img.opacity ?? 1.0;

      if (img.rotation !== 0) {
        baseCtx.translate(img.x, img.y);
        baseCtx.rotate(img.rotation);
        baseCtx.drawImage(cachedImg, 0, 0, img.w, img.h);
      } else {
        baseCtx.drawImage(cachedImg, img.x, img.y, img.w, img.h);
      }

      baseCtx.restore();

      if (isSelected && state.liveTransform && state.selectionBounds) {
        baseCtx.restore();
      }
    }
  }

  return boundsUpdates;
}

export function renderActiveLayer(
  activeCtx: CanvasRenderingContext2D,
  state: RenderState,
  viewport?: [number, number, number]
): void {
  const dpr = window.devicePixelRatio ?? 1;

  activeCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  activeCtx.clearRect(0, 0, activeCtx.canvas.width / dpr, activeCtx.canvas.height / dpr);

  if (viewport) {
    const [ox, oy, scale] = viewport;
    activeCtx.setTransform(dpr * scale, 0, 0, dpr * scale, ox * dpr, oy * dpr);
  }

  if (state.activeOutline && state.activeOutline.length >= 4) {
    if (state.shiftHeld && state.rawPointerScreen && viewport) {
        const [ox, oy, scale] = viewport;
        const startX = state.activeOutline[0];
        const startY = state.activeOutline[1];
        const px = (state.rawPointerScreen.x - ox) / scale;
        const py = (state.rawPointerScreen.y - oy) / scale;
        activeCtx.beginPath();
        activeCtx.moveTo(startX, startY);
        activeCtx.lineTo(px, py);
        activeCtx.strokeStyle = '#2563eb';
        activeCtx.lineWidth = 1.0 / scale;
        activeCtx.setLineDash([4 / scale, 4 / scale]);
        activeCtx.stroke();
        activeCtx.setLineDash([]);
    }
    drawOutlinePoints(activeCtx, state.activeOutline, state.activeColor, state.activeOpacity, state.activeTool);
  }

  if (state.eraserPos && state.rawPointerScreen && state.eraserRadius) {
    drawEraserCursor(activeCtx, state.rawPointerScreen, state.eraserRadius, dpr);
  }

  activeCtx.save();
  activeCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (state.marqueeRect) {
    const r = canvasToScreen(state.marqueeRect, viewport);
    activeCtx.strokeStyle = RENDER.SELECTION_COLOR;
    activeCtx.lineWidth = 1.5;
    activeCtx.setLineDash([6, 3]);
    activeCtx.lineDashOffset = -(Date.now() / 50) % 9;
    activeCtx.strokeRect(r.x, r.y, r.w, r.h);
    activeCtx.setLineDash([]);
  }

  if (state.selectionBounds && state.selectedIds && state.selectedIds.size > 0) {
    const b = canvasToScreen(state.selectionBounds, viewport);

    const tx = state.liveTransform?.translateX ?? 0;
    const ty = state.liveTransform?.translateY ?? 0;
    const scX = state.liveTransform?.scaleX ?? 1.0;
    const scY = state.liveTransform?.scaleY ?? 1.0;
    const ro = state.liveTransform?.rotation ?? 0;

    activeCtx.save();

    const vScale = viewport ? viewport[2] : 1;
    activeCtx.translate(b.x + b.w/2, b.y + b.h/2);
    activeCtx.rotate(ro);
    activeCtx.scale(scX, scY);
    activeCtx.translate(tx * vScale - b.w/2, ty * vScale - b.h/2);

    activeCtx.strokeStyle = RENDER.SELECTION_COLOR;
    activeCtx.lineWidth = 1.5;
    activeCtx.setLineDash([5, 3]);
    activeCtx.strokeRect(0, 0, b.w, b.h);
    activeCtx.setLineDash([]);

    const handles = getResizeHandlePositions(b.w, b.h);
    for (const h of handles) {
      activeCtx.fillStyle = '#ffffff';
      activeCtx.strokeStyle = RENDER.SELECTION_COLOR;
      activeCtx.lineWidth = 1.5;
      activeCtx.beginPath();
      activeCtx.rect(h.x - 4, h.y - 4, 8, 8);
      activeCtx.fill();
      activeCtx.stroke();
    }

    const ROTATE_HANDLE_OFFSET = RENDER.ROTATE_HANDLE_OFFSET_PX;
    activeCtx.beginPath();
    activeCtx.arc(b.w / 2, -ROTATE_HANDLE_OFFSET, 5, 0, Math.PI * 2);
    activeCtx.fillStyle = '#ffffff';
    activeCtx.strokeStyle = RENDER.SELECTION_COLOR;
    activeCtx.lineWidth = 1.5;
    activeCtx.fill();
    activeCtx.stroke();

    activeCtx.beginPath();
    activeCtx.moveTo(b.w / 2, 0);
    activeCtx.lineTo(b.w / 2, -ROTATE_HANDLE_OFFSET + 5);
    activeCtx.strokeStyle = RENDER.SELECTION_COLOR;
    activeCtx.lineWidth = 1;
    activeCtx.stroke();

    activeCtx.restore();
  }

  activeCtx.restore();
}

export function renderFrame(state: RenderState, viewport?: [number, number, number]): Array<{ id: number; w: number; h: number }> {
  let boundsUpdates: Array<{ id: number; w: number; h: number }> = [];
  if (state.baseDirty) {
    boundsUpdates = renderBaseLayer(state.baseCtx, state, viewport);
    state.baseDirty = false;
  }
  renderActiveLayer(state.activeCtx, state, viewport);
  return boundsUpdates;
}

function drawStroke(ctx: CanvasRenderingContext2D, stroke: StrokeData): void {
  if (stroke.outline_points.length < 2) return;
  ctx.save();
  ctx.globalAlpha = stroke.opacity;
  ctx.globalCompositeOperation = stroke.tool === 'highlighter' ? 'multiply' : 'source-over';
  const path = outlineToPath2D(stroke.outline_points);
  ctx.fillStyle = stroke.color;
  ctx.fill(path);
  ctx.restore();
}

function outlineToPath2D(points: number[][]): Path2D {
  const path = new Path2D();
  if (!points.length) return path;
  path.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) path.lineTo(points[i][0], points[i][1]);
  path.closePath();
  return path;
}

function drawOutlinePoints(
  ctx: CanvasRenderingContext2D,
  flatPts: Float64Array,
  color: string,
  opacity: number,
  tool: Tool
): void {
  ctx.save();
  ctx.globalAlpha = opacity;
  ctx.globalCompositeOperation = tool === 'highlighter' ? 'multiply' : 'source-over';

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(flatPts[0], flatPts[1]);
  for (let i = 2; i < flatPts.length; i += 2) {
    ctx.lineTo(flatPts[i], flatPts[i + 1]);
  }
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawEraserCursor(ctx: CanvasRenderingContext2D, pos: { x: number; y: number }, radius: number, dpr: number): void {
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.beginPath();
  ctx.arc(pos.x / dpr, pos.y / dpr, radius, 0, Math.PI * 2);
  ctx.strokeStyle = '#888';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([3, 3]);
  ctx.stroke();
  ctx.restore();
}

export function canvasToScreen(rect: {x: number, y: number, w: number, h: number}, viewport?: [number, number, number]) {
  const ox = viewport ? viewport[0] : 0;
  const oy = viewport ? viewport[1] : 0;
  const scale = viewport ? viewport[2] : 1;
  return {
    x: rect.x * scale + ox,
    y: rect.y * scale + oy,
    w: rect.w * scale,
    h: rect.h * scale,
  };
}

function getResizeHandlePositions(w: number, h: number) {
  return [
    {x: 0,   y: 0  },
    {x: w/2, y: 0  },
    {x: w,   y: 0  },
    {x: w,   y: h/2},
    {x: w,   y: h  },
    {x: w/2, y: h  },
    {x: 0,   y: h  },
    {x: 0,   y: h/2},
  ];
}
