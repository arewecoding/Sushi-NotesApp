/**
 * File Tree Store - For tree refresh signals
 */

import { writable } from 'svelte/store';

// Tree version - increments on each tree change to force re-render
export const treeVersion = writable(0);

/**
 * Increment tree version to trigger full tree re-render
 */
export function refreshTree(): void {
    treeVersion.update(v => v + 1);
}
