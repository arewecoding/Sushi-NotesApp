import type { CanvasEngine } from '$canvas-engine';
import { createEngineInstance } from './engine-loader';
import { logError } from './client/canvas';
import type { Tool } from './types';

export class DrawingEngine {
  private engine: CanvasEngine;

  private constructor(engine: CanvasEngine) {
    this.engine = engine;
  }

  static async create(): Promise<DrawingEngine> {
    const wasmEngine = await createEngineInstance();
    const de = new DrawingEngine(wasmEngine);

    // Global Svelte/JS uncaught error handler
    window.addEventListener('unhandledrejection', async (event) => {
      await logError(
        'svelte',
        event.reason?.toString() ?? 'unknown',
        event.reason?.stack ?? null
      ).catch(() => {});
    });

    return de;
  }

  private checkAndForwardWasmError(): void {
    const err = this.engine.get_last_error();
    if (err) {
      logError('rust_wasm', err).catch(() => {});
      this.engine.clear_last_error();
    }
  }

  beginStroke(x: number, y: number, pressure: number, time: number): void {
    this.engine.begin_stroke(x, y, pressure, time);
    this.checkAndForwardWasmError();
  }

  continueStroke(x: number, y: number, pressure: number, time: number, shiftHeld: boolean): Float64Array {
    const res = this.engine.continue_stroke(x, y, pressure, time, shiftHeld) as Float64Array;
    this.checkAndForwardWasmError();
    return res;
  }

  cancelStroke(): void {
    this.engine.cancel_stroke();
    this.checkAndForwardWasmError();
  }

  endStroke(): number {
    const res = this.engine.end_stroke();
    this.checkAndForwardWasmError();
    return res;
  }

  setColor(color: string): void {
    this.engine.set_color(color);
    this.checkAndForwardWasmError();
  }

  setSize(size: number): void {
    this.engine.set_size(size);
    this.checkAndForwardWasmError();
  }

  setTool(tool: Tool): void {
    this.engine.set_tool(tool);
    this.checkAndForwardWasmError();
  }

  undo(): boolean {
    const res = this.engine.undo();
    this.checkAndForwardWasmError();
    return res;
  }

  redo(): boolean {
    const res = this.engine.redo();
    this.checkAndForwardWasmError();
    return res;
  }

  canUndo(): boolean {
    return this.engine.can_undo();
  }

  canRedo(): boolean {
    return this.engine.can_redo();
  }

  hitTestPoint(x: number, y: number): number {
    return this.engine.hit_test_point(x, y) as number;
  }

  hitTestRect(x: number, y: number, w: number, h: number): number[] {
    return Array.from(this.engine.hit_test_rect(x, y, w, h));
  }

  hitTestMarquee(x: number, y: number, w: number, h: number): number[] {
    return Array.from(this.engine.hit_test_marquee(x, y, w, h));
  }

  setSelection(ids: number[]): void {
    this.engine.set_selection(new Float64Array(ids) as any);
    this.checkAndForwardWasmError();
  }

  addToSelection(ids: number[]): void {
    this.engine.add_to_selection(new Float64Array(ids) as any);
    this.checkAndForwardWasmError();
  }

  removeFromSelection(id: number): void {
    this.engine.remove_from_selection(id);
    this.checkAndForwardWasmError();
  }

  clearSelection(): void {
    this.engine.clear_selection();
    this.checkAndForwardWasmError();
  }

  /** Reset engine state: clears objects, undo/redo history, selection, and active stroke. */
  clear(): void {
    this.engine.clear();
    this.checkAndForwardWasmError();
  }

  getSelectedIds(): number[] {
    return Array.from(this.engine.get_selected_ids());
  }

  getSelectionBounds(): [number, number, number, number] | null {
    const b = Array.from(this.engine.get_selection_bounds());
    return b.length === 4 ? [b[0], b[1], b[2], b[3]] : null;
  }

  commitTransform(tx: number, ty: number, scaleX: number, scaleY: number, rotation: number): void {
    this.engine.commit_transform(tx, ty, scaleX, scaleY, rotation);
    this.checkAndForwardWasmError();
  }

  deleteSelected(): void {
    this.engine.delete_selected();
    this.checkAndForwardWasmError();
  }

  duplicateSelected(): void {
    this.engine.duplicate_selected();
    this.checkAndForwardWasmError();
  }

  setToolConfigs(json: string): boolean {
    const res = this.engine.set_tool_configs(json);
    this.checkAndForwardWasmError();
    return res;
  }

  getToolConfigs(): string {
    return this.engine.get_tool_configs();
  }

  replayStroke(rawPointsJson: string, configJson: string): number[] {
    const result = this.engine.replay_stroke(rawPointsJson, configJson);
    this.checkAndForwardWasmError();
    return Array.from(result);
  }

  getSelectedColorsJson(): string {
    return this.engine.get_selected_colors_json();
  }

  commitColorChange(originalColorsJson: string, newColor: string): void {
    this.engine.commit_color_change(originalColorsJson, newColor);
    this.checkAndForwardWasmError();
  }

  setSelectedColorPreview(color: string): void {
    this.engine.set_selected_color_preview(color);
    this.checkAndForwardWasmError();
  }

  getSelectedColor(): string | null {
    const c = this.engine.get_selected_color();
    return c === '' ? null : c;
  }

  getStrokesAt(x: number, y: number, radius: number): number[] {
    const arr = this.engine.get_strokes_at(x, y, radius);
    return Array.from(arr);
  }

  commitErase(ids: number[]): void {
    const arr = new Float64Array(ids);
    this.engine.commit_erase(arr);
    this.checkAndForwardWasmError();
  }

  pan(dx: number, dy: number): void {
    this.engine.pan(dx, dy);
    this.checkAndForwardWasmError();
  }

  zoom(factor: number, cx: number, cy: number): void {
    this.engine.zoom(factor, cx, cy);
    this.checkAndForwardWasmError();
  }

  resetViewport(): void {
    this.engine.reset_viewport();
    this.checkAndForwardWasmError();
  }

  getViewport(): [number, number, number] {
    const arr = this.engine.get_viewport();
    return [arr[0], arr[1], arr[2]];
  }

  exportSvg(width: number, height: number): string {
    return this.engine.export_svg(width, height);
  }

  serialize(): string {
    return this.engine.serialize();
  }

  deserialize(json: string): boolean {
    const res = this.engine.deserialize(json);
    this.checkAndForwardWasmError();
    return res;
  }

  addTextObjectWithContent(x: number, y: number, content: string, styleJson: string): number {
    const res = this.engine.add_text_object_with_content(x, y, content, styleJson);
    this.checkAndForwardWasmError();
    return res;
  }

  addTextObject(x: number, y: number): number {
    const res = this.engine.add_text_object(x, y);
    this.checkAndForwardWasmError();
    return res;
  }

  getTextObject(id: number): string {
    return this.engine.get_text_object(id);
  }

  updateTextContent(id: number, content: string): void {
    this.engine.update_text_content(id, content);
    this.checkAndForwardWasmError();
  }

  updateTextContentLive(id: number, content: string): void {
    this.engine.update_text_content_live(id, content);
    this.checkAndForwardWasmError();
  }

  updateTextStyle(id: number, styleJson: string): void {
    this.engine.update_text_style(id, styleJson);
    this.checkAndForwardWasmError();
  }

  deleteTextObject(id: number): void {
    this.engine.delete_text_object(id);
    this.checkAndForwardWasmError();
  }

  cancelTextObject(id: number): void {
    this.engine.cancel_text_object(id);
    this.checkAndForwardWasmError();
  }

  updateTextBounds(id: number, w: number, h: number): void {
    this.engine.update_text_bounds(id, w, h);
    this.checkAndForwardWasmError();
  }

  getAllObjects(): any[] {
    return this.engine.get_all_objects();
  }

  getObject(id: number): string {
    return this.engine.get_object(id);
  }

  cancelObject(id: number): void {
    this.engine.cancel_object(id);
    this.checkAndForwardWasmError();
  }

  hasSelection(): boolean {
    return this.engine.has_selection();
  }

  hitTestTextPoint(x: number, y: number): number {
    return this.engine.hit_test_text_point(x, y);
  }

  translateTextObject(id: number, dx: number, dy: number): void {
    this.engine.translate_text_object(id, dx, dy);
    this.checkAndForwardWasmError();
  }

  setSelectedTextId(id: number): void {
    this.engine.set_selected_text_id(id);
    this.checkAndForwardWasmError();
  }

  getSelectedTextId(): number {
    return this.engine.get_selected_text_id();
  }

  addImageObject(
    resourceId: string,
    x: number,
    y: number,
    w: number,
    h: number,
    origW: number,
    origH: number
  ): number {
    const res = this.engine.add_image_object(resourceId, x, y, w, h, origW, origH);
    this.checkAndForwardWasmError();
    return res;
  }

  // ─── Notebook Page Management ──────────────────────────────────────────────

  loadPage(json: string): boolean {
    const res = this.engine.load_page(json);
    this.checkAndForwardWasmError();
    return res;
  }

  serializePage(): string {
    return this.engine.serialize_page();
  }

  getCurrentPageId(): string {
    return this.engine.get_current_page_id();
  }

  setCurrentPageId(id: string): void {
    this.engine.set_current_page_id(id);
  }

  stashHistory(): void {
    this.engine.stash_history();
  }

  // ─── Shape Recognition (Phase 8) ──────────────────────────────────────────

  getLastCommittedStrokeId(): number {
    const id = this.engine.get_last_committed_stroke_id();
    this.checkAndForwardWasmError();
    return id;
  }

  checkForShape(strokeId: number): any | null {
    const jsonStr = this.engine.check_for_shape(strokeId);
    this.checkAndForwardWasmError();
    if (jsonStr) {
      try {
        return JSON.parse(jsonStr);
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  replaceStrokeWithShape(strokeId: number, shapeJson: string): boolean {
    try {
      this.engine.replace_stroke_with_shape(strokeId, shapeJson);
      this.checkAndForwardWasmError();
      return true;
    } catch (e) {
      console.warn("Failed to replace stroke with shape:", e);
      return false;
    }
  }

  setFeatureFlags(json: string): void {
    this.engine.set_feature_flags(json);
    this.checkAndForwardWasmError();
  }
}
