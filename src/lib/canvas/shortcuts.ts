import type { DrawingEngine } from './engine';
import type { CanvasAction } from './types';

export function setupShortcuts(engine: DrawingEngine, onAction: (action: CustomEvent<CanvasAction>) => void) {
  const handler = (e: KeyboardEvent) => {
    // Don't intercept keyboard events when user is typing in inputs, textareas, or contenteditable
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
      return;
    }
    if (e.target instanceof HTMLElement && e.target.isContentEditable) {
      return;
    }

    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      onAction(new CustomEvent('action', { detail: { type: 'undo' } }));
    } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      onAction(new CustomEvent('action', { detail: { type: 'redo' } }));
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      onAction(new CustomEvent('action', { detail: { type: 'redo' } }));
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      onAction(new CustomEvent('action', { detail: { type: 'delete' } }));
    } else if (e.key === 'Escape') {
      onAction(new CustomEvent('action', { detail: { type: 'clear' } }));
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
      e.preventDefault();
      onAction(new CustomEvent('action', { detail: { type: 'duplicate' } }));
    } else if (e.key.startsWith('Arrow')) {
      const step = e.shiftKey ? 10 : 1;
      if (e.key === 'ArrowUp') onAction(new CustomEvent('action', { detail: { type: 'nudge', dx: 0, dy: -step } }));
      else if (e.key === 'ArrowDown') onAction(new CustomEvent('action', { detail: { type: 'nudge', dx: 0, dy: step } }));
      else if (e.key === 'ArrowLeft') onAction(new CustomEvent('action', { detail: { type: 'nudge', dx: -step, dy: 0 } }));
      else if (e.key === 'ArrowRight') onAction(new CustomEvent('action', { detail: { type: 'nudge', dx: step, dy: 0 } }));
    } else {
      switch (e.key.toLowerCase()) {
        case 'p':
          onAction(new CustomEvent('action', { detail: { type: 'tool', tool: 'pen' } }));
          break;
        case 'e':
          onAction(new CustomEvent('action', { detail: { type: 'tool', tool: 'eraser' } }));
          break;
        case 'h':
          onAction(new CustomEvent('action', { detail: { type: 'tool', tool: 'highlighter' } }));
          break;
        case 'm':
          onAction(new CustomEvent('action', { detail: { type: 'tool', tool: 'marker' } }));
          break;
      }
    }
  };

  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
