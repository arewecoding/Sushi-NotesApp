/**
 * Block Drag Store — Hold-to-drag reordering for editor blocks
 *
 * Handles block drag state: which block is being dragged,
 * where it would be inserted, and active/inactive state.
 * Uses 300ms hold timer (same pattern as file tree drag).
 */

import { writable, get } from 'svelte/store';

/** Index of the block currently being dragged (-1 = none) */
export const dragBlockIndex = writable<number>(-1);

/** Index where the block would be inserted if dropped now (-1 = none) */
export const dropTargetIndex = writable<number>(-1);

/** Whether block drag is currently active */
export const isBlockDragging = writable<boolean>(false);

// Internal
let holdTimer: ReturnType<typeof setTimeout> | null = null;
let pendingIndex = -1;
const HOLD_DELAY_MS = 200; // slightly faster than file tree since it's a deliberate handle grab

function clearTimer() {
    if (holdTimer) {
        clearTimeout(holdTimer);
        holdTimer = null;
    }
}

/** Called when mousedown on a drag handle */
export function startBlockDrag(index: number) {
    pendingIndex = index;
    clearTimer();
    holdTimer = setTimeout(() => {
        dragBlockIndex.set(pendingIndex);
        dropTargetIndex.set(pendingIndex);
        isBlockDragging.set(true);
    }, HOLD_DELAY_MS);
}

/** Called on mouseenter of each block wrapper during drag */
export function updateDropTarget(index: number) {
    if (get(isBlockDragging)) {
        dropTargetIndex.set(index);
    }
}

/** Called on mouseup — returns [fromIndex, toIndex] if a reorder should happen, or null */
export function endBlockDrag(): [number, number] | null {
    clearTimer();
    const from = get(dragBlockIndex);
    const to = get(dropTargetIndex);

    dragBlockIndex.set(-1);
    dropTargetIndex.set(-1);
    isBlockDragging.set(false);
    pendingIndex = -1;

    if (from === -1 || to === -1 || from === to) return null;
    return [from, to];
}
