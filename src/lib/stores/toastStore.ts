/**
 * Toast Store - Simple notification system
 */

import { writable } from 'svelte/store';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
    id: number;
    type: ToastType;
    message: string;
}

let toastId = 0;

export const toasts = writable<Toast[]>([]);

/**
 * Add a toast notification
 */
export function addToast(type: ToastType, message: string, duration: number = 3000): void {
    const id = ++toastId;

    toasts.update(t => [...t, { id, type, message }]);

    // Auto-remove after duration
    setTimeout(() => {
        removeToast(id);
    }, duration);
}

/**
 * Remove a toast by id
 */
export function removeToast(id: number): void {
    toasts.update(t => t.filter(toast => toast.id !== id));
}
