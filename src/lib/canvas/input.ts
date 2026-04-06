export interface NormalizedPoint {
  x: number;
  y: number;
  pressure: number;
  timestamp: number;
  pointerType: 'mouse' | 'pen' | 'touch';
  shiftKey?: boolean;
}

export function normalizePointerEvent(
  e: PointerEvent,
  canvas: HTMLCanvasElement,
  viewport: [number, number, number]
): NormalizedPoint {
  const rect = canvas.getBoundingClientRect();
  const [offsetX, offsetY, scale] = viewport;

  // Client coords are in logical (CSS) pixels. The renderer applies the DPR transform,
  // so we only need to map logical screen pixels back to logical canvas space.
  const logicalX = e.clientX - rect.left;
  const logicalY = e.clientY - rect.top;
  const canvasX = (logicalX - offsetX) / scale;
  const canvasY = (logicalY - offsetY) / scale;

  // Real pressure for stylus/pen, neutral 0.5 for mouse (Rust simulates from velocity)
  const pressure = e.pointerType === 'pen' && e.pressure > 0 ? e.pressure : 0.5;

  return { x: canvasX, y: canvasY, pressure, timestamp: performance.now(), pointerType: e.pointerType as any, shiftKey: e.shiftKey };
}

function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}

// Coalesced events: capture all intermediate points for high-frequency devices (240hz stylus)
export function getCoalescedPoints(
  e: PointerEvent,
  canvas: HTMLCanvasElement,
  viewport: [number, number, number]
): NormalizedPoint[] {
  const coalesced = e.getCoalescedEvents?.() ?? [];
  const events = coalesced.length > 0 ? coalesced : [e];

  const startPressure = events[0].pressure;
  const endPressure = e.pressure;

  return events.map((ce, i) => {
    const t = events.length > 1 ? i / (events.length - 1) : 0;
    const pressure = ce.pressure > 0
        ? ce.pressure
        : lerp(startPressure, endPressure, t);

    const norm = normalizePointerEvent(ce as PointerEvent, canvas, viewport);
    if (ce.pointerType === 'pen') {
      norm.pressure = pressure;
    }
    return norm;
  });
}
