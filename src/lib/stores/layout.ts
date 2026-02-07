import { writable } from 'svelte/store';

export const isRightPanelOpen = writable(true);
export const isLeftPanelOpen = writable(true);
export const isSearchOpen = writable(false);
export const leftPanelWidth = writable(256);
export const rightPanelWidth = writable(256);
