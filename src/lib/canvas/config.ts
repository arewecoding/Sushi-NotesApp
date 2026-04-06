/** Sync: must match EngineConstants::text_line_height in canvas-engine/src/config.rs */
export const RENDER = {
  CANVAS_BACKGROUND: '#f0f0f0',
  TEXT_LINE_HEIGHT: 1.4,
  TEXT_INDICATOR_COLOR: '#4A90E2',
  SELECTION_COLOR: '#0099ff',
  ROTATE_HANDLE_OFFSET_PX: 24,
} as const;

/** Sync: must match EngineConstants defaults in canvas-engine/src/config.rs */
export const DEFAULTS = {
  COLOR: '#1a1a1a',
  FONT_FAMILY: 'system-ui',
  FONT_SIZE: 16,
  FONT_WEIGHT: 400,
  FONT_STYLE: 'normal',
  STROKE_SIZE: 8,
} as const;

export const INTERACTION = {
  HANDLE_HIT_THRESHOLD_PX: 12,
  ROTATE_HIT_THRESHOLD_PX: 12,
  SELECTION_EDGE_MARGIN_PX: 12,
  MARQUEE_DRAG_THRESHOLD_PX: 4,
  BLUR_SUPPRESS_MS: 200,
  EDITOR_FOCUS_DELAY_MS: 50,
  BLUR_COMMIT_DELAY_MS: 100,
} as const;
