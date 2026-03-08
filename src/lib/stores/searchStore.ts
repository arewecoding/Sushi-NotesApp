/**
 * Search Store — State management for the two-tier global search.
 *
 * Tier 1 (fast): keyword search over note titles + FTS5 block content
 * Tier 2 (deep): semantic search via FAISS embeddings
 */

import { writable, get } from 'svelte/store';
import { searchFast, searchDeep } from '$lib/client/apiClient';
import type { SearchResultItem } from '$lib/client/_apiTypes';

// ==========================================
// State
// ==========================================

export const searchResults = writable<SearchResultItem[]>([]);
export const searchTier = writable<'fast' | 'deep'>('fast');
export const searchLoading = writable(false);
export const selectedIndex = writable(-1);
export const lastQuery = writable('');

// Recent searches — persisted in localStorage
const RECENT_KEY = 'sushi_recent_searches';
const MAX_RECENT = 5;

function loadRecentSearches(): string[] {
    try {
        const raw = localStorage.getItem(RECENT_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch {
        return [];
    }
}

export const recentSearches = writable<string[]>(loadRecentSearches());

export function addRecentSearch(query: string): void {
    const trimmed = query.trim();
    if (!trimmed) return;

    recentSearches.update((prev) => {
        const filtered = prev.filter((q) => q !== trimmed);
        const updated = [trimmed, ...filtered].slice(0, MAX_RECENT);
        localStorage.setItem(RECENT_KEY, JSON.stringify(updated));
        return updated;
    });
}

// ==========================================
// Debounced Search
// ==========================================

let debounceTimer: ReturnType<typeof setTimeout> | null = null;
const DEBOUNCE_MS = 150;

/**
 * Run Tier 1 fast search with debouncing.
 */
export function performSearch(query: string): void {
    lastQuery.set(query);
    selectedIndex.set(-1);

    if (!query.trim()) {
        searchResults.set([]);
        searchTier.set('fast');
        searchLoading.set(false);
        return;
    }

    searchLoading.set(true);

    if (debounceTimer) clearTimeout(debounceTimer);

    debounceTimer = setTimeout(async () => {
        try {
            const response = await searchFast(query, 10);
            // Only update if this is still the current query
            if (get(lastQuery) === query) {
                searchResults.set(response.results);
                searchTier.set('fast');
            }
        } catch (err) {
            console.error('search_fast failed:', err);
            if (get(lastQuery) === query) {
                searchResults.set([]);
            }
        } finally {
            if (get(lastQuery) === query) {
                searchLoading.set(false);
            }
        }
    }, DEBOUNCE_MS);
}

/**
 * Switch to Tier 2 deep semantic search.
 */
export async function switchToDeep(query: string): Promise<void> {
    if (!query.trim()) return;

    searchLoading.set(true);
    searchTier.set('deep');
    selectedIndex.set(-1);

    try {
        const response = await searchDeep(query, 10);
        if (get(lastQuery) === query) {
            searchResults.set(response.results);
        }
    } catch (err) {
        console.error('search_deep failed:', err);
        if (get(lastQuery) === query) {
            searchResults.set([]);
        }
    } finally {
        if (get(lastQuery) === query) {
            searchLoading.set(false);
        }
    }
}

/**
 * Reset all search state (call when modal closes).
 */
export function resetSearch(): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    searchResults.set([]);
    searchTier.set('fast');
    searchLoading.set(false);
    selectedIndex.set(-1);
    lastQuery.set('');
}
