import type { DrawingEngine } from '../engine';
import { DEFAULTS, RENDER, INTERACTION } from '../config';
import { tick } from 'svelte';
import { canvasToScreen } from '../renderer';

type Viewport = [number, number, number];

export interface TextEditorState {
  editingTextId: number | null;
  overlayX: number;   // screen pixels
  overlayY: number;
  overlayW: number;
  fontFamily: string;
  fontSize: number;
  color: string;
  bold: boolean;
  italic: boolean;
  rotation: number;   // radians — CSS transform on overlay
}

export class TextEditorHandler {
  private state: TextEditorState;
  private engine: DrawingEngine;
  private editorEl: HTMLElement | null = null;
  public onAsyncCommit?: () => void;

  private textContentBeforeEdit: string = '';
  private blurTimeout: ReturnType<typeof setTimeout> | null = null;
  private suppressBlur: boolean = false;

  /** True when the current editing session is a brand-new object (created in beginNew) */
  private isNewObject: boolean = false;
  private canvasBounds: { x: number, y: number, w: number, fontSize: number } | null = null;

  constructor(engine: DrawingEngine) {
    this.engine = engine;
    this.state = {
      editingTextId: null,
      overlayX: 0,
      overlayY: 0,
      overlayW: 100,
      fontFamily: DEFAULTS.FONT_FAMILY,
      fontSize: DEFAULTS.FONT_SIZE,
      color: DEFAULTS.COLOR,
      bold: false,
      italic: false,
      rotation: 0,
    };
  }

  getState(): Readonly<TextEditorState> {
    return this.state;
  }

  updateViewport(viewport: Viewport): void {
    if (!this.canvasBounds || this.state.editingTextId === null) return;
    const { x, y, w, fontSize } = this.canvasBounds;
    const rect = canvasToScreen({ x, y, w: w || (fontSize * 2), h: 0 }, viewport);
    const halfLeading = (RENDER.TEXT_LINE_HEIGHT - 1.0) * fontSize * viewport[2] / 2;
    this.state.overlayX = rect.x;
    this.state.overlayY = rect.y - halfLeading;
    this.state.overlayW = rect.w;
    this.state.fontSize = fontSize * viewport[2];
  }

  attachEditorEl(el: HTMLElement | null): void {
    this.editorEl = el;
    if (el && this.state.editingTextId !== null) {
      // Re-populate innerText immediately in case Svelte recreated the DOM node
      try {
        const objStr = this.engine.getTextObject(this.state.editingTextId);
        const obj = JSON.parse(objStr);
        el.innerText = obj.content || '';
      } catch {}

      setTimeout(() => {
        if (this.editorEl && this.state.editingTextId !== null) {
          this.editorEl.focus();
          const range = document.createRange();
          range.selectNodeContents(this.editorEl);
          range.collapse(false);
          const sel = window.getSelection();
          sel?.removeAllRanges();
          sel?.addRange(range);
        }
      }, INTERACTION.EDITOR_FOCUS_DELAY_MS);
    }
  }

  /**
   * Create a brand-new text object in the engine immediately, select it,
   * and open the overlay for editing. The object starts with empty content;
   * on commit it is either kept (content typed) or cancelled (empty).
   */
  beginNew(canvasX: number, canvasY: number, viewport: Viewport, initStyleJson: string): void {
    if (this.state.editingTextId !== null) {
      this.commit();
    }

    // Create the engine object right away so selection handles appear
    const id = this.engine.addTextObjectWithContent(canvasX, canvasY, '', initStyleJson);
    this.engine.setSelection([id]);

    this.isNewObject = true;
    this.state.editingTextId = id;
    this.state.rotation = 0;
    this.textContentBeforeEdit = '';

    let parsedStyle: any = {};
    try { parsedStyle = JSON.parse(initStyleJson); } catch {}

    const fontSize = parsedStyle.font_size ?? DEFAULTS.FONT_SIZE;
    this.canvasBounds = { x: canvasX, y: canvasY, w: 0, fontSize };
    this.updateViewport(viewport);

    this.state.fontFamily = parsedStyle.font_family ?? DEFAULTS.FONT_FAMILY;
    this.state.color = parsedStyle.color ?? DEFAULTS.COLOR;

    const fw = parsedStyle.font_weight ?? DEFAULTS.FONT_WEIGHT;
    this.state.bold = typeof fw === 'string' ? fw.toLowerCase() === 'bold' : fw > 400;

    const fs = parsedStyle.font_style ?? DEFAULTS.FONT_STYLE;
    this.state.italic = typeof fs === 'string' ? fs.toLowerCase() === 'italic' : false;

    this.suppressBlur = true;
    setTimeout(() => { this.suppressBlur = false; }, INTERACTION.BLUR_SUPPRESS_MS);
  }

  beginEdit(textId: number, viewport: Viewport): void {
    if (this.blurTimeout !== null) { clearTimeout(this.blurTimeout); this.blurTimeout = null; }

    let objStr = "";
    try {
      objStr = this.engine.getTextObject(textId);
    } catch { return; }

    const obj = JSON.parse(objStr);
    if (!obj || !obj.id) return;

    const isContinuingEdit = this.state.editingTextId === textId;
    this.state.editingTextId = textId;

    if (!isContinuingEdit) {
      this.textContentBeforeEdit = obj.content || '';
      this.isNewObject = false;
    }

    // Always update overlay position / style from engine state
    const fontSize = obj.font_size ?? DEFAULTS.FONT_SIZE;
    this.canvasBounds = { x: obj.x, y: obj.y, w: obj.w ?? 0, fontSize };
    this.updateViewport(viewport);

    this.state.fontFamily = obj.font_family ?? DEFAULTS.FONT_FAMILY;
    this.state.color = obj.color ?? DEFAULTS.COLOR;
    this.state.rotation = obj.rotation ?? 0;

    const fw = obj.font_weight ?? DEFAULTS.FONT_WEIGHT;
    this.state.bold = typeof fw === 'string' ? fw.toLowerCase() === 'bold' : fw > 400;

    const fs = obj.font_style ?? DEFAULTS.FONT_STYLE;
    this.state.italic = typeof fs === 'string' ? fs.toLowerCase() === 'italic' : false;

    if (!isContinuingEdit) {
      this.suppressBlur = true;
      setTimeout(() => { this.suppressBlur = false; }, INTERACTION.BLUR_SUPPRESS_MS);

      const applyContent = () => {
          if (this.editorEl) {
              this.editorEl.innerText = obj.content;
              const range = document.createRange();
              const sel = window.getSelection();
              range.selectNodeContents(this.editorEl);
              range.collapse(false);
              sel?.removeAllRanges();
              sel?.addRange(range);
              this.editorEl.focus();
          } else if (this.state.editingTextId === textId) {
              setTimeout(applyContent, 10);
          }
      };

      tick().then(applyContent);
    }
  }

  onInput(e: Event): boolean {
    if (this.state.editingTextId !== null) {
      // Strip one trailing newline: contenteditable adds a phantom \n for trailing <br>/<div><br></div>
      const raw = (e.target as HTMLElement).innerText || '';
      const content = raw.endsWith('\n') ? raw.slice(0, -1) : raw;
      this.engine.updateTextContentLive(this.state.editingTextId, content);
      return true;
    }
    return false;
  }

  preventBlur(): void {
    if (this.blurTimeout !== null) {
      clearTimeout(this.blurTimeout);
      this.blurTimeout = null;
    }
    this.suppressBlur = true;
  }

  resumeFocus(): void {
    this.suppressBlur = false;
    if (this.editorEl && this.state.editingTextId !== null) {
      this.suppressBlur = true;
      this.editorEl.focus();
      setTimeout(() => { this.suppressBlur = false; }, INTERACTION.BLUR_SUPPRESS_MS);
    }
  }

  onBlur(relatedTarget?: EventTarget | null): void {
    if (this.suppressBlur) return;

    const related = relatedTarget as HTMLElement | null;
    if (related && related.closest('.canvas-toolbar')) {
      // Let the toolbar input receive focus, do not commit.
      return;
    }

    if (this.blurTimeout !== null) clearTimeout(this.blurTimeout);
    this.blurTimeout = setTimeout(() => {
      this.blurTimeout = null;
      if (this.state.editingTextId === null) return;

      const active = document.activeElement as HTMLElement | null;
      if (active && active.closest('.canvas-toolbar')) {
        // Active element is in the toolbar. Do not commit.
        return;
      }

      this.commit();
      if (this.onAsyncCommit) {
        this.onAsyncCommit();
      }
    }, INTERACTION.BLUR_COMMIT_DELAY_MS);
  }

  onKeydown(e: KeyboardEvent): boolean {
    if (this.state.editingTextId === null) return false;

    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      this.reset();
      return true;
    }

    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      this.commit();
      return true;
    }

    return false;
  }

  commit(): boolean {
    if (this.state.editingTextId === null) return false;
    const id = this.state.editingTextId;
    this.state.editingTextId = null;

    let content = this.editorEl?.innerText || '';

    // Check if the engine actually has text (Svelte might have wiped the DOM node during a reactive update)
    if (content.trim() === '') {
      try {
        const objStr = this.engine.getTextObject(id);
        const obj = JSON.parse(objStr);
        if (obj && obj.content && obj.content.trim() !== '') {
          content = obj.content;
        }
      } catch {}
    }

    content = content.replace(/\n{3,}/g, '\n\n').trimEnd();

    let historyChanged = false;

    if (content.trim() === '') {
      // Empty text — remove the object (and its history entry if new)
      this.engine.cancelTextObject(id);
      historyChanged = true;
    } else if (this.isNewObject) {
      // New object: cancel the initial empty placeholder, then create a clean
      // single-history-entry object with the final content + current style.
      const objStr = this.engine.getTextObject(id);
      const obj = JSON.parse(objStr);
      this.engine.cancelTextObject(id);
      this.engine.addTextObjectWithContent(obj.x, obj.y, content, JSON.stringify({
        font_family: obj.font_family,
        font_size: obj.font_size,
        font_weight: obj.font_weight,
        font_style: obj.font_style,
        color: obj.color,
        opacity: obj.opacity,
        rotation: obj.rotation,
      }));
      historyChanged = true;
    } else {
      // Existing object with changed content
      if (content !== this.textContentBeforeEdit) {
        this.engine.updateTextContent(id, content);
        historyChanged = true;
      }
    }

    this.isNewObject = false;
    this.engine.setSelectedTextId(-1);
    if (this.editorEl) this.editorEl.innerText = '';
    return historyChanged;
  }

  reset(): void {
    if (this.state.editingTextId === null) return;
    const id = this.state.editingTextId;
    this.state.editingTextId = null;

    // If it was a new object with no content, clean it up
    if (this.isNewObject) {
      this.engine.cancelTextObject(id);
    }
    this.isNewObject = false;
  }
}
