type Viewport = [number, number, number];
import type { DrawingEngine } from '../engine';
import { RENDER, INTERACTION } from '../config';

export type SelectionMode = "idle" | "marquee" | "dragging" | "resizing" | "rotating";

export interface SelectionHandlerState {
  mode: SelectionMode;
  marqueeStart: { x: number; y: number } | null;
  marqueeEnd: { x: number; y: number } | null;
  dragStart: { x: number; y: number } | null;
  activeHandle: number | null; // 0-7 for resize, 8 for rotate
  hoverCursor: string;
  liveTransform: { translateX: number; translateY: number; scaleX: number; scaleY: number; rotation: number } | null;
}

export class SelectionHandler {
  private state: SelectionHandlerState;
  private engine: DrawingEngine;
  private rotateStart: number = 0;
  private isTextOnlySubset: boolean = false;
  private imageAspectRatio: number | null = null;

  constructor(engine: DrawingEngine) {
    this.engine = engine;
    this.state = {
      mode: 'idle',
      marqueeStart: null,
      marqueeEnd: null,
      dragStart: null,
      activeHandle: null,
      hoverCursor: 'default',
      liveTransform: null,
    };
  }

  // Read by Canvas.svelte for rendering
  getState(): Readonly<SelectionHandlerState> {
    return this.state;
  }

  // Reset to idle (called on tool switch)
  reset(): void {
    this.state.mode = 'idle';
    this.state.marqueeStart = null;
    this.state.marqueeEnd = null;
    this.state.dragStart = null;
    this.state.activeHandle = null;
    this.state.hoverCursor = 'default';
    this.state.liveTransform = null;
  }

  private screenToBoxLocal(screenPt: {x:number, y:number}, bounds: [number, number, number, number], viewport: Viewport) {
    const b = {
      x: bounds[0] * viewport[2] + viewport[0],
      y: bounds[1] * viewport[2] + viewport[1],
      w: (bounds[2] - bounds[0]) * viewport[2],
      h: (bounds[3] - bounds[1]) * viewport[2]
    };
    const tx = this.state.liveTransform?.translateX ?? 0;
    const ty = this.state.liveTransform?.translateY ?? 0;
    const scX = this.state.liveTransform?.scaleX ?? 1.0;
    const scY = this.state.liveTransform?.scaleY ?? 1.0;
    const ro = this.state.liveTransform?.rotation ?? 0;

    const vScale = viewport[2];
    const cx = b.x + b.w/2 + tx * vScale;
    const cy = b.y + b.h/2 + ty * vScale;

    // Inverse translation
    let dx = screenPt.x - cx;
    let dy = screenPt.y - cy;
    // Inverse rotation
    const cosR = Math.cos(-ro);
    const sinR = Math.sin(-ro);
    let rx = dx * cosR - dy * sinR;
    let ry = dx * sinR + dy * cosR;
    // Inverse scale
    let sx = rx / scX;
    let sy = ry / scY;
    // Back to corner
    return { x: sx + b.w/2, y: sy + b.h/2, bw: b.w, bh: b.h };
  }

  private isNearRotateHandle(screenPt: {x:number, y:number}, bounds: [number, number, number, number], viewport: Viewport) {
    const local = this.screenToBoxLocal(screenPt, bounds, viewport);
    const hx = local.bw / 2;
    const hy = -RENDER.ROTATE_HANDLE_OFFSET_PX;
    return Math.hypot(local.x - hx, local.y - hy) < INTERACTION.ROTATE_HIT_THRESHOLD_PX;
  }

  private getHandleIndexAtPoint(screenPt: {x:number, y:number}, bounds: [number, number, number, number], viewport: Viewport) {
    const local = this.screenToBoxLocal(screenPt, bounds, viewport);
    const w = local.bw;
    const h = local.bh;
    const handles = [
      {x: 0,   y: 0  },
      {x: w/2, y: 0  },
      {x: w,   y: 0  },
      {x: w,   y: h/2},
      {x: w,   y: h  },
      {x: w/2, y: h  },
      {x: 0,   y: h  },
      {x: 0,   y: h/2},
    ];
    for (let i = 0; i < handles.length; i++) {
        if (Math.abs(local.x - handles[i].x) < INTERACTION.HANDLE_HIT_THRESHOLD_PX && Math.abs(local.y - handles[i].y) < INTERACTION.HANDLE_HIT_THRESHOLD_PX) {
            return i;
        }
    }
    return -1;
  }

  private computeResizeScale(handleIdx: number, start: {x:number, y:number}, current: {x:number, y:number}, bounds: [number, number, number, number] | null, shiftKey: boolean = false) {
      if (!bounds) return {scaleX: 1.0, scaleY: 1.0, translateX: 0, translateY: 0};
      const bx = bounds[0], by = bounds[1];
      const bw = bounds[2] - bounds[0], bh = bounds[3] - bounds[1];
      const cx = bx + bw / 2, cy = by + bh / 2;
      const hw = bw / 2, hh = bh / 2;
      
      const isCorner = handleIdx % 2 === 0;
      const isHorizontal = handleIdx === 3 || handleIdx === 7;
  
      const isOnlyText = this.isTextOnlySubset;

      if (isCorner) {
        // Anchor is opposite corner
        // 0=TL→anchor=BR, 2=TR→anchor=BL, 4=BR→anchor=TL, 6=BL→anchor=TR
        const anchorX = (handleIdx === 0 || handleIdx === 6) ? bx + bw : bx;
        const anchorY = (handleIdx === 0 || handleIdx === 2) ? by + bh : by;

        const startDx = Math.abs(start.x - anchorX);
        const startDy = Math.abs(start.y - anchorY);
        if (startDx < 0.001 || startDy < 0.001) return {scaleX: 1.0, scaleY: 1.0, translateX: 0, translateY: 0};

        const dx = Math.abs(current.x - anchorX);
        const dy = Math.abs(current.y - anchorY);
        let sx = dx / startDx;
        let sy = dy / startDy;

        if (shiftKey) {
            const ratio = this.imageAspectRatio !== null ? this.imageAspectRatio : (bh / bw);
            const deltaX = Math.abs(current.x - start.x);
            const deltaY = Math.abs(current.y - start.y);

            let targetW = bw * sx;
            let targetH = bh * sy;

            if (deltaX > deltaY) {
                targetH = targetW * ratio;
                sy = targetH / bh;
            } else {
                targetW = targetH / ratio;
                sx = targetW / bw;
            }
        }

        const tx = (anchorX - cx) * (1 / sx - 1);
        const ty = (anchorY - cy) * (1 / sy - 1);
        return {scaleX: sx, scaleY: sy, translateX: tx, translateY: ty};
      } else if (isHorizontal) {
        // Handle 3 (right): anchor = left edge. Handle 7 (left): anchor = right edge.
        const anchorX = handleIdx === 3 ? bx : bx + bw;
        const startDist = Math.abs(start.x - anchorX);
        const currentDist = Math.abs(current.x - anchorX);
        if (startDist < 0.001) return {scaleX: 1.0, scaleY: 1.0, translateX: 0, translateY: 0};
        const sx = currentDist / startDist;
        const tx = (anchorX - cx) * (1 / sx - 1);
        if (isOnlyText) {
            const sy = Math.abs(sx);
            return {scaleX: sx, scaleY: sy, translateX: tx, translateY: 0};
        }
        return {scaleX: sx, scaleY: 1.0, translateX: tx, translateY: 0};
      } else {
        // Handle 1 (top): anchor = bottom edge. Handle 5 (bottom): anchor = top edge.
        const anchorY = handleIdx === 1 ? by + bh : by;
        const startDist = Math.abs(start.y - anchorY);
        const currentDist = Math.abs(current.y - anchorY);
        if (startDist < 0.001) return {scaleX: 1.0, scaleY: 1.0, translateX: 0, translateY: 0};
        const sy = currentDist / startDist;
        const ty = (anchorY - cy) * (1 / sy - 1);
        if (isOnlyText) {
            const sx = Math.abs(sy);
            return {scaleX: sx, scaleY: sy, translateX: 0, translateY: ty};
        }
        return {scaleX: 1.0, scaleY: sy, translateX: 0, translateY: ty};
      }
  }

  private isPointInBounds(canvasPt: {x:number, y:number}, bounds: [number, number, number, number]) {
    return canvasPt.x >= bounds[0] && canvasPt.y >= bounds[1] && canvasPt.x <= bounds[2] && canvasPt.y <= bounds[3];
  }

  private isNearBoundingBoxEdge(screenPt: {x:number, y:number}, bounds: [number, number, number, number], viewport: Viewport): boolean {
    const local = this.screenToBoxLocal(screenPt, bounds, viewport);
    const w = local.bw;
    const h = local.bh;
    const t = INTERACTION.SELECTION_EDGE_MARGIN_PX;
    // Check if near any of the 4 edges but not inside (excluding a margin inward)
    const inX = local.x >= -t && local.x <= w + t;
    const inY = local.y >= -t && local.y <= h + t;
    if (!inX || !inY) return false;
    // Near top or bottom edge
    if (local.y < t || local.y > h - t) return true;
    // Near left or right edge
    if (local.x < t || local.x > w - t) return true;
    return false;
  }

  onPointerDown(x: number, y: number, viewport: Viewport, isMultiSelect: boolean): boolean {
    const screenX = x * viewport[2] + viewport[0];
    const screenY = y * viewport[2] + viewport[1];
    const screenPt = { x: screenX, y: screenY };
    const canvasPt = { x, y };

    const bounds = this.engine.getSelectionBounds();

    if (bounds && this.isNearRotateHandle(screenPt, bounds, viewport)) {
      this.state.mode = 'rotating';
      const cx = bounds[0] + (bounds[2] - bounds[0]) / 2;
      const cy = bounds[1] + (bounds[3] - bounds[1]) / 2;
      this.rotateStart = Math.atan2(canvasPt.y - cy, canvasPt.x - cx);
      this.state.activeHandle = 8;
      return true;
    }

    if (bounds) {
      const hi = this.getHandleIndexAtPoint(screenPt, bounds, viewport);
      if (hi !== -1) {
        this.state.mode = 'resizing';
        this.state.activeHandle = hi;
        this.state.dragStart = { x: canvasPt.x, y: canvasPt.y };
        
        this.isTextOnlySubset = false;
        this.imageAspectRatio = null;
        const selectedIds = this.engine.getSelectedIds();
        if (selectedIds.length > 0) {
            this.isTextOnlySubset = true;
            let imageCount = 0;
            let lastImageObj: any = null;
            const objs = this.engine.getAllObjects();
            for (const obj of objs) {
                if (selectedIds.includes(obj.id)) {
                    if (obj.object_type !== 'text') {
                        this.isTextOnlySubset = false;
                    }
                    if (obj.object_type === 'image') {
                        imageCount++;
                        lastImageObj = obj;
                    }
                }
            }
            if (imageCount === 1 && selectedIds.length === 1 && lastImageObj) {
                this.imageAspectRatio = lastImageObj.original_h / lastImageObj.original_w;
            }
        }
        
        return true;
      }
    }

    if (bounds && this.isPointInBounds(canvasPt, bounds)) {
      this.state.mode = 'dragging';
      this.state.dragStart = { x: canvasPt.x, y: canvasPt.y };
      this.state.liveTransform = { translateX:0, translateY:0, scaleX:1, scaleY:1, rotation:0 };
      return true;
    }

    const hit = this.engine.hitTestPoint(canvasPt.x, canvasPt.y);
    if (hit >= 0) {
      if (isMultiSelect) {
        if (this.engine.getSelectedIds().includes(hit)) {
          this.engine.removeFromSelection(hit);
        } else {
          this.engine.addToSelection([hit]);
        }
      } else {
        this.engine.setSelection([hit]);
      }
      return true;
    }

    this.engine.clearSelection();
    this.engine.setSelectedTextId(-1);
    this.state.mode = 'marquee';
    this.state.marqueeStart = { x: canvasPt.x, y: canvasPt.y };
    this.state.marqueeEnd = { x: canvasPt.x, y: canvasPt.y };
    this.state.liveTransform = null;
    return true;
  }

  onPointerMove(x: number, y: number, viewport: Viewport, isHover: boolean, shiftKey: boolean = false): boolean {
    const canvasPt = { x, y };
    
    if (isHover) {
      if (this.state.mode !== 'idle') return false;
      const screenX = x * viewport[2] + viewport[0];
      const screenY = y * viewport[2] + viewport[1];
      const logicalScreenPt = { x: screenX, y: screenY };
      const bounds = this.engine.getSelectionBounds();
      let newCursor = 'default';
      
      if (bounds) {
        if (this.isNearRotateHandle(logicalScreenPt, bounds, viewport)) {
          newCursor = 'rotate';
        } else {
          const hi = this.getHandleIndexAtPoint(logicalScreenPt, bounds, viewport);
          if (hi !== -1) {
             const cursors = ['nwse-resize', 'ns-resize', 'nesw-resize', 'ew-resize', 'nwse-resize', 'ns-resize', 'nesw-resize', 'ew-resize'];
             newCursor = cursors[hi] || 'default';
          } else if (this.isNearBoundingBoxEdge(logicalScreenPt, bounds, viewport)) {
             newCursor = 'grab';
          }
        }
      }
      if (this.state.hoverCursor !== newCursor) {
         this.state.hoverCursor = newCursor;
         return true;
      }
      return false;
    }

    switch (this.state.mode) {
      case 'marquee':
        this.state.marqueeEnd = { x: canvasPt.x, y: canvasPt.y };
        return true;

      case 'dragging':
        if (this.state.dragStart) {
          this.state.liveTransform = {
            translateX: canvasPt.x - this.state.dragStart.x,
            translateY: canvasPt.y - this.state.dragStart.y,
            scaleX: 1.0,
            scaleY: 1.0,
            rotation: 0.0,
          };
          return true;
        }
        break;

      case 'resizing':
        if (this.state.activeHandle !== null && this.state.dragStart) {
            const { scaleX: rsX, scaleY: rsY, translateX: rsTx, translateY: rsTy } = this.computeResizeScale(
              this.state.activeHandle,
              this.state.dragStart,
              canvasPt,
              this.engine.getSelectionBounds(),
              shiftKey
            );
            this.state.liveTransform = {
              translateX: rsTx,
              translateY: rsTy,
              scaleX: rsX,
              scaleY: rsY,
              rotation: 0,
            };
            return true;
        }
        break;

      case 'rotating':
        const bounds = this.engine.getSelectionBounds();
        if (!bounds) break;
        const cx = bounds[0] + (bounds[2] - bounds[0]) / 2;
        const cy = bounds[1] + (bounds[3] - bounds[1]) / 2;
        const currentAngle = Math.atan2(canvasPt.y - cy, canvasPt.x - cx);
        this.state.liveTransform = {
          translateX: 0,
          translateY: 0,
          scaleX: 1.0,
          scaleY: 1.0,
          rotation: currentAngle - this.rotateStart,
        };
        return true;
    }
    return false;
  }

  onPointerUp(x: number, y: number, viewport: Viewport): boolean {
    let requiresFullUpdate = false;
    switch (this.state.mode) {
      case 'marquee':
        if (this.state.marqueeStart && this.state.marqueeEnd) {
          const mx = Math.min(this.state.marqueeStart.x, this.state.marqueeEnd.x);
          const my = Math.min(this.state.marqueeStart.y, this.state.marqueeEnd.y);
          const mw = Math.abs(this.state.marqueeStart.x - this.state.marqueeEnd.x);
          const mh = Math.abs(this.state.marqueeStart.y - this.state.marqueeEnd.y);

          if (mw > INTERACTION.MARQUEE_DRAG_THRESHOLD_PX / viewport[2] && mh > INTERACTION.MARQUEE_DRAG_THRESHOLD_PX / viewport[2]) {
             const ids = this.engine.hitTestMarquee(mx, my, mw, mh);
             this.engine.setSelection(ids);
          }
        }
        this.state.marqueeStart = null;
        this.state.marqueeEnd = null;
        requiresFullUpdate = true;
        break;

      case 'dragging':
      case 'resizing':
      case 'rotating':
        if (this.state.liveTransform) {
          const { translateX, translateY, scaleX, scaleY, rotation } = this.state.liveTransform;
          const moved = Math.abs(translateX) > 0.5 || Math.abs(translateY) > 0.5 || Math.abs(scaleX - 1.0) > 0.001 || Math.abs(scaleY - 1.0) > 0.001 || Math.abs(rotation) > 0.001;
                     
          if (moved) {
            // For resizing, the live preview translate compensates center-based
            // CSS scaling (it's applied INSIDE the scale context). The engine
            // applies translate AFTER scale, so we must multiply by the scale
            // factor to get the same final position: commitTx = scaleX * tx.
            const commitTx = this.state.mode === 'resizing' ? scaleX * translateX : translateX;
            const commitTy = this.state.mode === 'resizing' ? scaleY * translateY : translateY;
            this.engine.commitTransform(commitTx, commitTy, scaleX, scaleY, rotation);
            requiresFullUpdate = true;
          }
          this.state.liveTransform = null;
        }
        break;
    }

    this.state.mode = 'idle';
    this.state.activeHandle = null;
    return requiresFullUpdate;
  }

  // Called by Canvas.svelte keyboard handler
  onNudge(dx: number, dy: number): boolean {
    const ids = this.engine.getSelectedIds();
    if (ids.length > 0) {
      this.engine.commitTransform(dx, dy, 1, 1, 0);
      return true;
    }
    return false;
  }
}
