import { writable } from 'svelte/store';
import { getFeatureFlags } from './client/canvas';

export const featureFlags = writable<Record<string, any>>({});

export async function initFlags() {
    try {
        const flags = await getFeatureFlags();
        featureFlags.set(flags);
    } catch (e) {
        console.warn("Failed to load feature flags:", e);
    }
}
