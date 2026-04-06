/**
 * settingsStore.ts — Simple writable store for settings modal visibility.
 */
import { writable } from "svelte/store";

export const isSettingsOpen = writable(false);

export function openSettings() {
    isSettingsOpen.set(true);
}

export function closeSettings() {
    isSettingsOpen.set(false);
}
