import type { DrawingEngine } from '../engine';

type Viewport = [number, number, number];

export interface GestureResult {
  type: 'none' | 'pan' | 'pinch';
  newViewport?: Viewport;
}

export class GestureHandler {
  private pointers: Map<number, { x: number; y: number }> = new Map();
  private lastMidX: number = 0;
  private lastMidY: number = 0;
  private lastDist: number = 0;
  private ignoreUntilAllReleased: boolean = false;

  constructor(private engine: DrawingEngine) {}

  onPointerDown(e: PointerEvent): boolean {
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (this.ignoreUntilAllReleased) return true;

    if (this.pointers.size === 2) {
      const pts = Array.from(this.pointers.values());
      this.lastMidX = (pts[0].x + pts[1].x) / 2;
      this.lastMidY = (pts[0].y + pts[1].y) / 2;
      this.lastDist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
      return true;
    }
    
    // Do not consume the first finger down
    return false;
  }

  onPointerMove(e: PointerEvent, canvasRect: DOMRect): GestureResult {
    if (this.pointers.has(e.pointerId)) {
      this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    if (this.ignoreUntilAllReleased) return { type: 'none' };

    if (this.pointers.size === 2) {
      const pts = Array.from(this.pointers.values());
      const midX = (pts[0].x + pts[1].x) / 2;
      const midY = (pts[0].y + pts[1].y) / 2;
      const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);

      const panDX = midX - this.lastMidX;
      const panDY = midY - this.lastMidY;
      
      let type: 'none' | 'pan' | 'pinch' = 'none';

      if (Math.abs(panDX) > 0 || Math.abs(panDY) > 0) {
        this.engine.pan(panDX, panDY);
        type = 'pan';
      }

      if (this.lastDist > 0 && dist > 0) {
        const zoomFactor = dist / this.lastDist;
        if (Math.abs(zoomFactor - 1.0) > 0.001) {
          this.engine.zoom(zoomFactor, midX - canvasRect.left, midY - canvasRect.top);
          type = 'pinch';
        }
      }

      this.lastMidX = midX;
      this.lastMidY = midY;
      this.lastDist = dist;

      return { type, newViewport: this.engine.getViewport() };
    }

    return { type: 'none' };
  }

  onPointerUp(e: PointerEvent): boolean {
    this.pointers.delete(e.pointerId);

    if (this.pointers.size === 0) {
      this.ignoreUntilAllReleased = false;
    } else if (!this.ignoreUntilAllReleased) {
      this.ignoreUntilAllReleased = true;
    }
    
    return true; // The 'up' event of a gesture should be consumed, though Svelte only calls if active
  }

  onPointerCancel(e: PointerEvent): boolean {
    return this.onPointerUp(e);
  }

  isGestureActive(): boolean {
    return this.pointers.size >= 2;
  }
  
  shouldIgnore(): boolean {
    return this.ignoreUntilAllReleased;
  }

  onWheel(e: WheelEvent, canvasRect: DOMRect): Viewport {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const delta = e.deltaY * (e.deltaMode === 1 ? 20 : 1);
      const zoomFactor = Math.pow(0.999, delta);
      const originX = e.clientX - canvasRect.left;
      const originY = e.clientY - canvasRect.top;
      this.engine.zoom(zoomFactor, originX, originY);
    } else if (e.shiftKey) {
      this.engine.pan(-e.deltaY, 0);
    } else {
      this.engine.pan(-e.deltaX, -e.deltaY);
    }
    return this.engine.getViewport();
  }

  reset(): void {
    this.pointers.clear();
    this.lastDist = 0;
    this.ignoreUntilAllReleased = false;
  }
}
