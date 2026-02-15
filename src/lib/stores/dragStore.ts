/**
 * Drag Store — Hold-to-drag system
 * 
 * Press and HOLD mousedown for 300ms → drag mode activates.
 * Quick clicks pass through normally to onclick handlers.
 * 
 * HTML5 Drag and Drop doesn't work in WebView2 on Windows,
 * so we use this custom mouse-event-based system instead.
 */

import { writable, get } from 'svelte/store';

export interface DragItem {
    id: string;
    type: 'note' | 'dir';
    name: string;
}

/** Currently dragged item (null = not dragging) */
export const dragItem = writable<DragItem | null>(null);

/** Current mouse position during drag */
export const dragPosition = writable<{ x: number; y: number }>({ x: 0, y: 0 });

/** Directory path being hovered over during drag (for visual feedback + drop target) */
export const dragOverDir = writable<string | null>(null);

// Internal state
let pendingItem: DragItem | null = null;
let holdTimer: ReturnType<typeof setTimeout> | null = null;
const HOLD_DELAY_MS = 300;

function clearHoldTimer() {
    if (holdTimer) {
        clearTimeout(holdTimer);
        holdTimer = null;
    }
}

/**
 * Called on mousedown — starts hold timer.
 * Drag only activates after 300ms hold.
 * Quick clicks (<300ms) never enter drag mode.
 */
export function startDrag(item: DragItem, e: MouseEvent) {
    pendingItem = item;
    const x = e.clientX;
    const y = e.clientY;

    clearHoldTimer();
    holdTimer = setTimeout(() => {
        if (pendingItem) {
            dragItem.set(pendingItem);
            dragPosition.set({ x, y });
            // Change cursor to indicate drag mode
            document.body.style.cursor = 'grabbing';
        }
    }, HOLD_DELAY_MS);
}

/**
 * Called on every mousemove (via window listener).
 * Updates position only when drag is active.
 */
export function updateDragPosition(e: MouseEvent) {
    if (get(dragItem)) {
        dragPosition.set({ x: e.clientX, y: e.clientY });
    }
}

/**
 * Called on mouseup — ends drag and clears all state.
 * If drag never activated (quick click), this is a no-op.
 */
export function endDrag() {
    clearHoldTimer();
    document.body.style.cursor = '';
    dragItem.set(null);
    dragOverDir.set(null);
    pendingItem = null;
}
