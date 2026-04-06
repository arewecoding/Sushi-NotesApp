/**
 * Canvas IPC client — typed wrapper around pyInvoke.
 *
 * All canvas IPC calls must go through canvasInvoke, never raw pyInvoke.
 * This ensures consistent error handling and response envelope unwrapping.
 */

import { pyInvoke } from 'tauri-plugin-pytauri-api';

// ─── Response envelope types ───────────────────────────────────────────

type ApiResponse<T> =
  | { status: 'ok'; data: T }
  | { status: 'error'; code: string; message: string };

// ─── Central error handler ─────────────────────────────────────────────

function canvasErrorHandler(code: string, message: string): void {
  console.error(`Canvas API error [${code}]: ${message}`);
  // TODO: emit to error notification store for UI display
}

// ─── Core invoke wrapper ───────────────────────────────────────────────

export async function canvasInvoke<T>(command: string, payload?: unknown): Promise<T> {
  const response = await pyInvoke(command, payload ?? {}) as ApiResponse<T>;
  if (response.status === 'error') {
    canvasErrorHandler(response.code, response.message);
    throw new Error(`[${response.code}] ${response.message}`);
  }
  return response.data;
}

// ─── Typed command wrappers ────────────────────────────────────────────

export interface SaveResult {
  path?: string;
  cancelled?: boolean;
}

export interface LoadResult {
  state?: string;
  path?: string;
  cancelled?: boolean;
}

export async function saveCanvas(stateJson: string): Promise<SaveResult> {
  // TODO: wire up
  return {};
}

export async function loadCanvas(): Promise<LoadResult> {
  // TODO: wire up
  return {};
}

export async function saveSvg(svgContent: string): Promise<SaveResult> {
  // TODO: wire up
  return {};
}

export async function logError(
  source: string,
  message: string,
  stack?: string | null
): Promise<void> {
  // TODO: wire up
  console.error(`[Canvas Error] ${source}: ${message}\n${stack}`);
}

// ─── Device profile config commands ────────────────────────────────────

export interface StrokeConfigResult {
  config: Record<string, unknown> | null;
  is_default: boolean;
}

export async function getStrokeConfig(pointerType: string): Promise<StrokeConfigResult> {
  // TODO: wire up
  return { config: null, is_default: true };
}

export async function saveStrokeConfig(
  pointerType: string,
  config: Record<string, unknown>
): Promise<void> {
  // TODO: wire up
}

export async function getFeatureFlags(): Promise<Record<string, any>> {
  // TODO: wire up
  return {};
}

// ─── Image import commands ─────────────────────────────────────────────

export interface ImageImportResult {
  resource_id: string;
  width: number;
  height: number;
  path: string;
}

export async function importCanvasImage(
  imageData: number[],
  filename: string,
  canvasPath?: string
): Promise<ImageImportResult> {
  // TODO: wire up
  return { resource_id: '', width: 0, height: 0, path: '' };
}

export async function getResourceBytes(
  resourceId: string,
  canvasPath?: string
): Promise<{ data: number[] }> {
  // TODO: wire up
  return { data: [] };
}

// ─── Notebook Commands ───────────────────────────────────────────────────

import type { BookInfo, PageData, PageSummary } from '../types';

export async function createBook(title: string, pageSizePreset: string = 'A4'): Promise<{ book_id: string; path: string; first_page_id: string; cancelled?: boolean }> {
  // TODO: wire up
  return { book_id: '', path: '', first_page_id: '' };
}

export async function openBook(path: string): Promise<BookInfo> {
  // TODO: wire up
  return {} as BookInfo;
}

export async function getPage(bookId: string, pageId: string): Promise<PageData> {
  // TODO: wire up
  return {} as PageData;
}

export async function updatePage(bookId: string, pageId: string, pageDataJson: string): Promise<void> {
  // TODO: wire up
}

export async function addPage(bookId: string, afterPageId: string, name?: string): Promise<PageSummary> {
  // TODO: wire up
  return {} as PageSummary;
}

export async function deletePage(bookId: string, pageId: string): Promise<void> {
  // TODO: wire up
}

export async function renamePage(bookId: string, pageId: string, name: string): Promise<void> {
  // TODO: wire up
}

export async function reorderPages(bookId: string, orderedPageIds: string[]): Promise<void> {
  // TODO: wire up
}
