/**
 * File Tree Store - Persistent expanded state + refresh signals
 */

import { writable } from 'svelte/store';

/**
 * Persistent set of expanded directory paths.
 * '__root__' represents the vault root and starts expanded.
 */
export const expandedDirs = writable<Set<string>>(new Set(['__root__']));

/**
 * Tree data version — incremented on structural changes.
 * Expanded nodes react by re-fetching their contents.
 */
export const treeVersion = writable(0);

/**
 * Toggle a directory's expanded/collapsed state.
 */
export function toggleDir(dirKey: string): void {
    expandedDirs.update(dirs => {
        const next = new Set(dirs);
        if (next.has(dirKey)) {
            next.delete(dirKey);
        } else {
            next.add(dirKey);
        }
        return next;
    });
}

/**
 * Increment tree version to signal expanded nodes to re-fetch data.
 * Does NOT destroy any components.
 */
export function refreshTree(): void {
    treeVersion.update(v => v + 1);
}
