/**
 * layoutStore.ts
 * ==============
 * UI-layout state: open/closed panels, panel widths, active right-panel tab,
 * and search modal visibility. These writable stores are consumed by the
 * three layout components (NavRail, LeftPanel, RightPanel) and the SearchModal.
 */
import { writable } from 'svelte/store';

export const isRightPanelOpen = writable(true);
export const isLeftPanelOpen = writable(true);
export const isSearchOpen = writable(false);
export const leftPanelWidth = writable(256);
export const rightPanelWidth = writable(300);
export const rightPanelTab = writable<'details' | 'chat'>('chat');

