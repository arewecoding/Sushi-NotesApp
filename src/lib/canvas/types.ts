import type { DrawingEngine } from './engine';

export type Tool = 'pen' | 'eraser' | 'highlighter' | 'marker' | 'cursor' | 'select' | 'text';

export type CanvasAction = 
  | { type: 'nudge'; dx: number; dy: number }
  | { type: 'delete' }
  | { type: 'clear' }
  | { type: 'duplicate' }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'tool'; tool: Tool };

export interface StrokeData {
  object_type: 'stroke';
  id: number;
  outline_points: number[][];
  color: string;
  opacity: number;
  tool: Tool;
  aabb: [number, number, number, number];
}

export interface TextObjectData {
  object_type: 'text';
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  content: string;
  font_family: string;
  font_size: number;
  font_weight: number;
  font_style: string;
  color: string;
  opacity: number;
  align: string;
  rotation: number;
}

export interface ImageObjectData {
  object_type: 'image';
  id: number;
  resource_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  original_w: number;
  original_h: number;
  opacity: number;
  rotation: number;
}

export type CanvasObjectData = StrokeData | TextObjectData | ImageObjectData;

export interface RenderState {
  baseCtx: CanvasRenderingContext2D;
  activeCtx: CanvasRenderingContext2D;
  objects: CanvasObjectData[];
  activeOutline: Float64Array | null;
  activeColor: string;
  activeOpacity: number;
  activeTool: Tool;
  eraserPos: { x: number; y: number; radius: number } | null;
  rawPointerScreen?: { x: number; y: number };
  shiftHeld?: boolean;
  eraserRadius?: number;
  highlightedIds: Set<number>;

  // Selection
  selectionBounds: { x: number; y: number; w: number; h: number } | null;
  liveTransform: {
    translateX: number;
    translateY: number;
    scaleX: number;
    scaleY: number;
    rotation: number;
  } | null;
  selectedIds: Set<number>;
  marqueeRect: { x: number; y: number; w: number; h: number } | null;

  baseDirty: boolean;

  // Text
  selectedTextId: number;
  editingTextId: number | null;

  imageCache: Map<string, HTMLImageElement>;
}

// ─── Notebook Types ─────────────────────────────────────────────────────────

export interface BookMetadata {
  file_id: string;
  title: string;
  created_at: string;
  last_modified: string;
  version: string;
  mode: 'notebook';
}

export interface PageSummary {
  page_id: string;
  name: string;
  order: number;
}

export interface PageSize {
  preset: string;
  width_mm: number;
  height_mm: number;
}

export interface BookInfo {
  book_id: string;
  metadata: BookMetadata;
  page_size: PageSize;
  pages: PageSummary[];
  path: string;
}

export interface BackgroundConfig {
  type: "none" | "dots" | "grid" | "lines" | "ruled" | "dotted" | "cornell" | "music_staff" | "isometric";
  color: string;
  spacing: number;
}

export interface PageData {
  page_id: string;
  name: string;
  order: number;
  background: { type: string; color?: string; spacing?: number };
  strokes: StrokeData[];
  text_objects: TextObjectData[];
  image_objects: ImageObjectData[];
}

