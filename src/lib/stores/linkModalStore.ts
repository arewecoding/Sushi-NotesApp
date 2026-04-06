/**
 * linkModalStore.ts
 * =================
 * Lightweight store managing the Link Modal's open/close state
 * and the context needed to insert a link back into the editor.
 */

import { writable } from "svelte/store";

export interface LinkModalContext {
    /** Pre-populated display text (from selection or empty) */
    displayText: string;
    /** Block the link will be inserted into */
    blockId: string;
    /** Callback invoked with the final [[...]] syntax string */
    insertionCallback: (syntax: string) => void;
}

export const isLinkModalOpen = writable(false);
export const linkModalContext = writable<LinkModalContext | null>(null);

export function openLinkModal(context: LinkModalContext): void {
    linkModalContext.set(context);
    isLinkModalOpen.set(true);
}

export function closeLinkModal(): void {
    isLinkModalOpen.set(false);
    linkModalContext.set(null);
}
