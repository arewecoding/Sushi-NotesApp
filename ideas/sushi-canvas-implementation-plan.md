# Sushi Canvas — Complete Implementation Plan
### A Living Engineering Document for Antigravity

> This document is the single source of truth for all canvas development work. Each phase is self-contained and written as a direct engineering brief. Phases must be executed in order unless explicitly noted as parallelizable. Every section includes the exact files to touch, the exact data structures to define, the exact contracts to maintain, and the known pitfalls to avoid.

---

## Table of Contents

1. [Phase 0 — Foundation & Infrastructure](#phase-0--foundation--infrastructure)
2. [Phase 1 — Critical Bug Fixes](#phase-1--critical-bug-fixes)
3. [Phase 2 — Select Tool](#phase-2--select-tool)
4. [Phase 3 — Color Change for Selected Objects](#phase-3--color-change-for-selected-objects)
5. [Phase 4 — Config Struct & ML Calibration Readiness](#phase-4--config-struct--ml-calibration-readiness)
6. [Phase 5 — Text Tool](#phase-5--text-tool)
7. [Phase 6 — Image Import](#phase-6--image-import)
8. [Phase 7 — .jbook Format (Named Pages)](#phase-7--jbook-format-named-pages)
9. [Phase 8 — Straight Line & Shape Recognition](#phase-8--straight-line--shape-recognition)
10. [Phase 9 — Background Patterns](#phase-9--background-patterns)
11. [Phase 10 — Gesture & Input Expansion](#phase-10--gesture--input-expansion)
12. [Phase 11 — Canvas-as-a-Block Integration](#phase-11--canvas-as-a-block-integration)
13. [Phase 12 — Infinite Canvas as Vault File](#phase-12--infinite-canvas-as-vault-file)
14. [Phase 13 — PDF Annotation Canvas](#phase-13--pdf-annotation-canvas)
15. [Phase 14 — Canvas Snippets & Deep Linking](#phase-14--canvas-snippets--deep-linking)
16. [Phase 15 — ML Calibration System](#phase-15--ml-calibration-system)
17. [Phase 16 — Quality of Life Polish](#phase-16--quality-of-life-polish)
18. [Appendix A — Rust Engine Architecture Reference](#appendix-a--rust-engine-architecture-reference)
19. [Appendix B — IPC Command Reference](#appendix-b--ipc-command-reference)
20. [Appendix C — File Format Schemas](#appendix-c--file-format-schemas)

---

## Phase 0 — Foundation & Infrastructure

**Goal:** Establish the logging, error handling, config, crash safety, and schema versioning infrastructure that every subsequent phase depends on. Nothing else should be built before this is done. This phase is entirely invisible to the user but is load-bearing for everything that follows.

---

### 0.1 — Structured Logging

**Why:** The canvas app has three separate runtime environments (Python, Rust WASM, Svelte) that can all fail independently. Without unified logging, debugging production issues requires guessing which layer broke.

**Python — `structlog` setup**

Install: add `structlog` to `pyproject.toml` dependencies.

Create `sushi_canvas/logging_config.py`:

```python
import structlog
import logging
import os
from pathlib import Path

LOG_DIR = Path.home() / ".sushi" / "logs"

def configure_logging(level: str = "INFO"):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Rotating file handler — 5MB per file, keep 5 files
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        LOG_DIR / "sushi-canvas.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    handler.setLevel(getattr(logging, level))
    logging.basicConfig(handlers=[handler], level=getattr(logging, level))
```

Call `configure_logging()` at the very top of the app entry point, before any other imports.

Usage pattern in every Python file:
```python
import structlog
log = structlog.get_logger(__name__)

# In methods:
log.info("canvas_saved", canvas_id=canvas_id, stroke_count=len(strokes))
log.warning("resource_missing", path=str(path))
log.error("save_failed", error=str(e), canvas_id=canvas_id)
```

**Rust WASM — error forwarding**

Rust WASM cannot write to a file. Instead, expose a method on the engine that JS can call to forward errors to Python:

In `engine.rs`, add:
```rust
#[wasm_bindgen]
pub fn get_last_error(&self) -> Option<String> {
    self.last_error.clone()
}

#[wasm_bindgen]
pub fn clear_last_error(&mut self) {
    self.last_error = None;
}
```

Add `last_error: Option<String>` field to the engine struct. Any `unwrap()` or panic-prone operation should set this field rather than panicking.

**Svelte — global error handler + forwarding**

In `src/lib/canvas/engine.ts`, add after engine initialization:

```typescript
// Forward WASM errors to Python backend every 10 seconds
setInterval(async () => {
    const err = engine.get_last_error();
    if (err) {
        await pyInvoke("log_error_cmd", { 
            source: "rust_wasm", 
            message: err,
            timestamp: new Date().toISOString()
        });
        engine.clear_last_error();
    }
}, 10_000);

// Global Svelte/JS uncaught error handler
window.addEventListener("unhandledrejection", async (event) => {
    await pyInvoke("log_error_cmd", {
        source: "svelte",
        message: event.reason?.toString() ?? "unknown",
        stack: event.reason?.stack ?? null,
        timestamp: new Date().toISOString()
    });
});
```

**Python IPC handler — `log_error_cmd`**

In `commands.py`:
```python
@app.command()
async def log_error_cmd(payload: LogErrorPayload) -> OkResponse:
    log.error("client_error", source=payload.source, message=payload.message)
    return ok({})
```

**Log level discipline — NEVER log inside hot paths:**
- Never log inside the pointer event handler
- Never log inside the stroke rendering loop
- Never log inside WASM calls
- Log at stroke commit (pointerup), at save, at load, at error

---

### 0.2 — IPC Error Envelope

**Why:** Currently every IPC command probably has ad-hoc error handling. A consistent envelope means the Svelte side handles all errors in one place.

**Python — define in `models.py` (create this file):**

```python
from pydantic import BaseModel
from typing import Any, Optional

class OkResponse(BaseModel):
    status: str = "ok"
    data: Any = None

class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str
    detail: Optional[Any] = None

def ok(data: Any = None) -> dict:
    return OkResponse(data=data).model_dump()

def err(code: str, message: str, detail: Any = None) -> dict:
    return ErrorResponse(code=code, message=message, detail=detail).model_dump()
```

Error codes to define now (add to as needed):
- `CANVAS_NOT_FOUND`
- `SAVE_FAILED`
- `LOAD_FAILED`
- `INVALID_PAYLOAD`
- `RESOURCE_MISSING`
- `ENGINE_ERROR`

Every IPC command must return either `ok(data)` or `err(code, message)`. No raw exceptions should escape a command handler — wrap with try/except at the handler level.

**Svelte — `pyInvoke` wrapper in `src/lib/client/canvas.ts`:**

```typescript
type ApiResponse<T> = { status: "ok"; data: T } | { status: "error"; code: string; message: string };

async function canvasInvoke<T>(command: string, payload?: unknown): Promise<T> {
    const response: ApiResponse<T> = await pyInvoke(command, payload ?? {});
    if (response.status === "error") {
        // Route to central error handler
        canvasErrorHandler(response.code, response.message);
        throw new Error(`[${response.code}] ${response.message}`);
    }
    return response.data;
}

function canvasErrorHandler(code: string, message: string) {
    // For now: console.error + toast notification
    // Later: route to error store for UI display
    console.error(`Canvas API error [${code}]: ${message}`);
    // TODO: emit to error notification store
}
```

All canvas IPC calls in Svelte components must go through `canvasInvoke`, never raw `pyInvoke`.

---

### 0.3 — Crash-Safe File Writing

**Why:** If the app crashes mid-write, the canvas file becomes corrupted. This is unrecoverable data loss.

**Python — `filesys.py`, add `atomic_write`:**

```python
import tempfile
import os
from pathlib import Path

def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically. Original is untouched if write fails."""
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file in same directory (same filesystem = atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)  # Atomic on POSIX, best-effort on Windows
    except Exception:
        os.unlink(tmp_path)  # Clean up temp file
        raise
```

Every canvas and note save must go through `atomic_write`. No direct `open(path, "w").write()` anywhere in the codebase.

---

### 0.4 — Schema Version & Migration Runner

**Why:** Your `.jcanvas` files have `"version": "1.0"`. Without a migration system, any schema change requires either breaking all existing files or writing ad-hoc compat code scattered everywhere.

**Python — `migrations.py`:**

```python
from typing import Callable
import structlog

log = structlog.get_logger(__name__)

# Registry: version string -> migration function
CANVAS_MIGRATIONS: dict[str, Callable[[dict], dict]] = {}
BOOK_MIGRATIONS: dict[str, Callable[[dict], dict]] = {}

CURRENT_CANVAS_VERSION = "1.0"
CURRENT_BOOK_VERSION = "1.0"

def register_canvas_migration(from_version: str):
    def decorator(fn: Callable[[dict], dict]):
        CANVAS_MIGRATIONS[from_version] = fn
        return fn
    return decorator

def migrate_canvas(data: dict) -> dict:
    """Run all needed migrations on a canvas data dict. Returns migrated dict."""
    version = data.get("metadata", {}).get("version", "1.0")
    while version in CANVAS_MIGRATIONS:
        log.info("migrating_canvas", from_version=version)
        data = CANVAS_MIGRATIONS[version](data)
        version = data["metadata"]["version"]
    return data

# Example migration (for future use):
# @register_canvas_migration("1.0")
# def migrate_1_0_to_1_1(data: dict) -> dict:
#     data["metadata"]["version"] = "1.1"
#     # ... transform data ...
#     return data
```

Call `migrate_canvas(data)` immediately after loading any `.jcanvas` file, before handing data to any other system.

---

### 0.5 — Feature Flags

**Python — `flags.py`:**

```python
import json
from pathlib import Path
from typing import Any
import structlog

log = structlog.get_logger(__name__)

FLAGS_PATH = Path.home() / ".sushi" / "flags.json"

_flags: dict[str, Any] = {}

def load_flags() -> None:
    global _flags
    if FLAGS_PATH.exists():
        try:
            _flags = json.loads(FLAGS_PATH.read_text())
            log.info("flags_loaded", flags=_flags)
        except Exception as e:
            log.warning("flags_load_failed", error=str(e))
            _flags = {}
    else:
        _flags = {}

def flag(name: str, default: bool = False) -> bool:
    return bool(_flags.get(name, default))
```

Call `load_flags()` at startup. Usage: `if flag("select_tool_enabled"): ...`

Initial flags to define in `~/.sushi/flags.json`:
```json
{
    "select_tool_enabled": true,
    "text_tool_enabled": false,
    "image_import_enabled": false,
    "jbook_enabled": false,
    "shape_recognition_enabled": false,
    "pdf_annotation_enabled": false,
    "ml_calibration_enabled": false
}
```

---

### 0.6 — Rust Engine: Add `metadata` Field to `Stroke`

**Why:** This is the most important schema decision in this entire document. The current `Stroke` struct has no way to carry a block reference, link URL, or any annotation metadata. Retrofitting this after strokes are serialized in hundreds of files is a painful breaking change. Adding an optional field now costs almost nothing.

**In `stroke.rs`:**

```rust
use std::collections::HashMap;
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Stroke {
    pub id: u64,
    pub points: Vec<InputPoint>,
    pub outline: Vec<[f32; 2]>,
    pub color: [f32; 4],      // RGBA, 0.0-1.0
    pub width: f32,
    pub tool: ToolType,
    pub opacity: f32,
    
    // Phase 0 addition — optional arbitrary metadata
    // Use for: block references, link URLs, annotation tags, OCR text
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, Value>>,
}
```

The `#[serde(default, skip_serializing_if = "Option::is_none")]` means existing files without this field deserialize fine, and files without metadata don't waste bytes serializing `null`.

Similarly add to `TextObject` and `ImageObject` when those are created.

---

### 0.7 — Performance Baseline Instrumentation

**Python — wrap key operations with timing in `filesys.py`:**

```python
import time
import structlog

log = structlog.get_logger(__name__)

def timed(operation_name: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.debug("perf", operation=operation_name, elapsed_ms=round(elapsed_ms, 2))
            return result
        return wrapper
    return decorator

# Usage:
@timed("canvas_load")
def load_canvas(path: Path) -> dict:
    ...

@timed("canvas_save")  
def save_canvas(path: Path, data: dict) -> None:
    ...
```

This creates a baseline. When something becomes slow, you'll have historical log data to compare against.

---

### Phase 0 Checklist for Antigravity

- [ ] `structlog` added to dependencies, `logging_config.py` created, called at startup
- [ ] `log_error_cmd` IPC handler created in `commands.py`
- [ ] WASM `get_last_error` / `clear_last_error` methods added to engine
- [ ] JS error forwarding interval and unhandledrejection handler set up
- [ ] `models.py` created with `ok()` / `err()` envelope functions
- [ ] All existing IPC commands wrapped with try/except and returning envelopes
- [ ] `canvasInvoke` wrapper in `canvas.ts`
- [ ] `atomic_write` in `filesys.py`, all save calls migrated to it
- [ ] `migrations.py` created with empty registry
- [ ] `migrate_canvas()` called on every canvas file load
- [ ] `flags.py` created and loaded at startup
- [ ] `Stroke` struct has `metadata: Option<HashMap<String, Value>>`
- [ ] `@timed` decorator wrapping `load_canvas` and `save_canvas`

---

## Phase 1 — Critical Bug Fixes

**Goal:** Fix the two known correctness bugs before building any new features. These erode trust in the tool.

---

### 1.1 — Drag Bug: Object Not Following Bounding Box

**Description:** When dragging a selected object, the object's visual position does not follow the bounding box correctly. The bounding box moves but the stroke rendering lags, snaps, or diverges.

**Diagnostic questions for Antigravity to answer before implementing:**

1. Is the transform applied in JS (visual-only during drag) and committed to Rust on `pointerup`? If so, is the JS transform being applied to the rendered outline points directly, or via a canvas `ctx.setTransform()` call?
2. Is the bounding box computed from the *original* outline points or from the *transformed* points during drag?
3. Is the bounding box re-computed on every frame during drag, or is it cached at drag start and translated?
4. When the drag commits to Rust, are the points being transformed in Rust coordinate space or screen space?

**Expected root cause:** The bounding box is being translated in screen space but the stroke outline render is still using original Rust-space coordinates without applying the in-flight transform, creating a visual split.

**Fix architecture:**

Drag must follow a strict two-phase pattern:

**Phase A — Visual (JS only, every frame):**
```typescript
// On pointermove during drag:
const dx = currentX - dragStartX;
const dy = currentY - dragStartY;

// DO NOT touch Rust. Only apply a CSS/canvas transform to the active layer.
activeCtx.save();
activeCtx.translate(dx, dy);
renderSelectedStrokes(activeCtx, selectedStrokeOutlines); // render originals with offset
activeCtx.restore();

// Bounding box moves by the same dx, dy — computed from cached start bbox
renderBoundingBox(cachedStartBbox.translated(dx, dy));
```

**Phase B — Commit (Rust, on pointerup only):**
```typescript
// On pointerup:
const dx = finalX - dragStartX;
const dy = finalY - dragStartY;

// Convert dx, dy from screen space to canvas space
const [cdx, cdy] = screenToCanvas(dx, dy);

// Single Rust call to commit
engine.translate_selected(cdx, cdy);

// Full re-render from Rust state
rerenderAll();
```

**Rust — `translate_selected` in `engine.rs`:**
```rust
pub fn translate_selected(&mut self, dx: f32, dy: f32) {
    for id in &self.selected_ids {
        if let Some(stroke) = self.strokes.iter_mut().find(|s| s.id == *id) {
            for point in stroke.outline.iter_mut() {
                point[0] += dx;
                point[1] += dy;
            }
            for point in stroke.points.iter_mut() {
                point.x += dx;
                point.y += dy;
            }
            // Invalidate cached bbox for this stroke
            self.stroke_bboxes.remove(id);
        }
    }
    // Push to undo history
    self.history.push(HistoryEntry::TranslateStrokes { 
        ids: self.selected_ids.clone(), dx, dy 
    });
}
```

**Coordinate space note:** All transform operations in Rust must work in canvas coordinate space (not screen/pixel space). The JS layer is responsible for converting screen deltas to canvas deltas using the current viewport scale before calling any Rust transform method.

```typescript
function screenToCanvas(dx: number, dy: number): [number, number] {
    const scale = engine.get_viewport_scale();
    return [dx / scale, dy / scale];
}
```

---

### 1.2 — Three-Finger Gesture Response

**Decision:** Three fingers = undo, four fingers = redo. This matches Procreate, GoodNotes, and Apple's system-level conventions. Stylus users will have muscle memory for this.

**Current state:** Three-finger behavior is undefined (the pointer state machine probably ignores it or conflicts).

**Implementation — in `src/lib/canvas/input.ts`:**

The pointer state machine needs a `finger_count` tracker:

```typescript
let activePointers = new Map<number, PointerEvent>();

canvas.addEventListener("pointerdown", (e) => {
    activePointers.set(e.pointerId, e);
    handlePointerCountChange(activePointers.size);
});

canvas.addEventListener("pointerup", (e) => {
    activePointers.delete(e.pointerId);
});

canvas.addEventListener("pointercancel", (e) => {
    activePointers.delete(e.pointerId);
});

function handlePointerCountChange(count: number) {
    if (count === 3) {
        // Undo
        engine.undo();
        rerenderAll();
        // Consume event — prevent any stroke from starting
        cancelActiveDraw();
    } else if (count === 4) {
        // Redo
        engine.redo();
        rerenderAll();
        cancelActiveDraw();
    } else if (count === 2) {
        // Existing pinch-to-zoom / pan — already handled
    }
}
```

**Critical:** When a 3-finger or 4-finger gesture is detected, any in-progress stroke must be cancelled immediately. A stroke that was started with 1 finger before the second and third fingers arrived should be discarded, not committed.

```typescript
function cancelActiveDraw() {
    if (isDrawing) {
        engine.cancel_active_stroke(); // Add this to Rust engine
        isDrawing = false;
        clearActiveLayer();
    }
}
```

**Rust — add `cancel_active_stroke` to `engine.rs`:**
```rust
pub fn cancel_active_stroke(&mut self) {
    self.active_stroke_points.clear();
    // Do NOT push to history — this was never committed
}
```

---

### Phase 1 Checklist for Antigravity

- [ ] Drag bug root cause confirmed via diagnostic questions
- [ ] Two-phase drag implemented: JS visual transform on pointermove, single Rust commit on pointerup
- [ ] `translate_selected` implemented in Rust with undo history entry
- [ ] `screenToCanvas` coordinate conversion utility in `input.ts`
- [ ] Three-finger = undo, four-finger = redo implemented in pointer state machine
- [ ] `cancel_active_stroke` in Rust engine, called when multi-finger gesture detected
- [ ] `cancelActiveDraw` in JS, clears active layer and resets draw state

---

## Phase 2 — Select Tool

**Goal:** A complete, professional-grade select tool. This is the largest single feature in the canvas codebase. It must be architected carefully because nearly everything else (color change, transform, text editing, image manipulation) depends on it.

---

### 2.1 — Rust Engine Changes

**New fields on the engine struct:**

```rust
pub struct CanvasEngine {
    // ... existing fields ...
    
    pub selected_ids: HashSet<u64>,
    pub selection_bbox: Option<BoundingBox>,   // Cached, invalidated on change
    
    // In-flight transform state (for undo grouping)
    transform_start_positions: HashMap<u64, Vec<[f32; 2]>>,  // stroke_id -> original outline
}
```

**New structs:**

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BoundingBox {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}

impl BoundingBox {
    pub fn union(a: &BoundingBox, b: &BoundingBox) -> BoundingBox { ... }
    pub fn contains_point(&self, x: f32, y: f32) -> bool { ... }
    pub fn contains_bbox(&self, other: &BoundingBox) -> bool { ... }
    pub fn center(&self) -> (f32, f32) { ... }
    pub fn expanded_by(&self, margin: f32) -> BoundingBox { ... }
}
```

**New history entries:**

```rust
pub enum HistoryEntry {
    // ... existing entries ...
    TranslateStrokes { ids: HashSet<u64>, dx: f32, dy: f32 },
    ScaleStrokes { ids: HashSet<u64>, cx: f32, cy: f32, sx: f32, sy: f32 },
    RotateStrokes { ids: HashSet<u64>, cx: f32, cy: f32, angle_rad: f32 },
    DuplicateStrokes { original_ids: HashSet<u64>, new_ids: HashSet<u64> },
    DeleteStrokes { strokes: Vec<Stroke> },  // store full strokes for undo
}
```

**New WASM-exported methods:**

```rust
// Selection
pub fn hit_test_point(&self, x: f32, y: f32, threshold: f32) -> Option<u64>
pub fn hit_test_marquee(&self, x: f32, y: f32, w: f32, h: f32) -> Vec<u64>
pub fn select_stroke(&mut self, id: u64)
pub fn deselect_stroke(&mut self, id: u64)
pub fn select_strokes(&mut self, ids: Vec<u64>)
pub fn select_all(&mut self)
pub fn deselect_all(&mut self)
pub fn get_selection_bbox(&self) -> Option<BoundingBox>

// Transforms (commit to Rust state — always in canvas space)
pub fn translate_selected(&mut self, dx: f32, dy: f32)
pub fn scale_selected(&mut self, cx: f32, cy: f32, sx: f32, sy: f32)
pub fn rotate_selected(&mut self, cx: f32, cy: f32, angle_rad: f32)

// Transform start/end (for undo grouping across multiple frames)
pub fn begin_transform(&mut self)   // Save pre-transform positions
pub fn commit_transform(&mut self)  // Push single undo entry for entire gesture

// Operations
pub fn delete_selected(&mut self)
pub fn duplicate_selected(&mut self) -> Vec<u64>  // Returns new stroke IDs
pub fn get_selected_ids(&self) -> Vec<u64>
```

**`hit_test_point` implementation detail:**

Do not test against bounding boxes. Test against the actual stroke outline polygon using point-in-polygon for filled strokes, or distance-to-polyline for thin strokes:

```rust
pub fn hit_test_point(&self, x: f32, y: f32, threshold: f32) -> Option<u64> {
    // Test in reverse order (topmost stroke first)
    for stroke in self.strokes.iter().rev() {
        let bbox = self.get_stroke_bbox(stroke.id);
        
        // Early reject: not even in bounding box
        if !bbox.expanded_by(threshold).contains_point(x, y) {
            continue;
        }
        
        // Precise test: point in outline polygon
        if point_in_polygon(x, y, &stroke.outline) {
            return Some(stroke.id);
        }
        
        // Fallback: distance to outline boundary (for thin strokes)
        if min_distance_to_polyline(x, y, &stroke.outline) < threshold {
            return Some(stroke.id);
        }
    }
    None
}
```

**`hit_test_marquee` implementation:**

A stroke is included in marquee selection only if its ENTIRE bounding box is within the marquee rectangle. Partial overlap does not select. This matches Figma, Illustrator, and Procreate behavior.

```rust
pub fn hit_test_marquee(&self, x: f32, y: f32, w: f32, h: f32) -> Vec<u64> {
    let marquee = BoundingBox { x, y, w, h };
    self.strokes.iter()
        .filter(|s| {
            let bbox = self.get_stroke_bbox(s.id);
            marquee.contains_bbox(&bbox)
        })
        .map(|s| s.id)
        .collect()
}
```

**Bounding box caching:**

Computing bounding boxes for every stroke on every hit test is expensive. Cache them:

```rust
stroke_bboxes: HashMap<u64, BoundingBox>,  // Invalidated when stroke is modified

fn get_stroke_bbox(&mut self, id: u64) -> BoundingBox {
    if let Some(cached) = self.stroke_bboxes.get(&id) {
        return cached.clone();
    }
    let stroke = self.strokes.iter().find(|s| s.id == id).unwrap();
    let bbox = compute_bbox(&stroke.outline);
    self.stroke_bboxes.insert(id, bbox.clone());
    bbox
}
```

---

### 2.2 — JS Pointer State Machine for Select Mode

The existing pointer state machine handles: `idle`, `drawing`, `panning`, `pinching`. Add select-specific states:

```typescript
type SelectState = 
    | "idle"
    | "marquee"           // Dragging a selection rectangle
    | "dragging"          // Moving selected strokes
    | "resizing"          // Pulling a resize handle
    | "rotating"          // Rotating via rotate handle
    | "hover_selected"    // Mouse over a selected stroke (show move cursor)
    | "hover_handle"      // Mouse over a resize/rotate handle
```

**State transitions:**

```
idle + pointerdown on empty space → begin marquee
idle + pointerdown on unselected stroke → select it + begin drag
idle + pointerdown on selected stroke → begin drag
idle + pointerdown on resize handle → begin resize
idle + pointerdown on rotate handle → begin rotate
idle + pointermove (no button) → hit test handles → update cursor

marquee + pointermove → update marquee rect → render marching ants
marquee + pointerup → commit marquee selection → idle

dragging + pointermove → JS visual transform only (DO NOT call Rust)
dragging + pointerup → commit_transform() to Rust → rerenderAll → idle

resizing + pointermove → JS visual transform only
resizing + pointerup → commit_transform() to Rust → rerenderAll → idle

rotating + pointermove → JS visual rotation only
rotating + pointerup → commit_transform() to Rust → rerenderAll → idle
```

---

### 2.3 — Bounding Box UI Rendering

Render the bounding box on the active layer, not the base layer. It must be redrawn every frame during transforms.

**8 resize handles + 1 rotate handle:**

```typescript
interface Handle {
    type: "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw" | "rotate";
    x: number;  // screen space
    y: number;
    cursor: string;
}

function computeHandles(bbox: BoundingBox, viewport: Viewport): Handle[] {
    // Convert bbox corners to screen space
    const [sx, sy] = canvasToScreen(bbox.x, bbox.y, viewport);
    const [ex, ey] = canvasToScreen(bbox.x + bbox.w, bbox.y + bbox.h, viewport);
    const mx = (sx + ex) / 2;
    const my = (sy + ey) / 2;
    
    const HANDLE_OFFSET = 24; // px above bbox top for rotate handle
    
    return [
        { type: "nw", x: sx, y: sy, cursor: "nw-resize" },
        { type: "n",  x: mx, y: sy, cursor: "n-resize" },
        { type: "ne", x: ex, y: sy, cursor: "ne-resize" },
        { type: "e",  x: ex, y: my, cursor: "e-resize" },
        { type: "se", x: ex, y: ey, cursor: "se-resize" },
        { type: "s",  x: mx, y: ey, cursor: "s-resize" },
        { type: "sw", x: sx, y: ey, cursor: "sw-resize" },
        { type: "w",  x: sx, y: my, cursor: "w-resize" },
        { type: "rotate", x: mx, y: sy - HANDLE_OFFSET, cursor: "grab" },
    ];
}

function renderBoundingBox(ctx: CanvasRenderingContext2D, handles: Handle[]) {
    // Dashed selection box
    ctx.save();
    ctx.strokeStyle = "#4A90E2";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 3]);
    // ... draw rect from handles ...
    
    // Draw handles as filled squares with border
    ctx.setLineDash([]);
    for (const handle of handles) {
        if (handle.type === "rotate") {
            // Circle for rotate handle
            ctx.beginPath();
            ctx.arc(handle.x, handle.y, 6, 0, Math.PI * 2);
            ctx.fillStyle = "white";
            ctx.fill();
            ctx.strokeStyle = "#4A90E2";
            ctx.stroke();
        } else {
            ctx.fillStyle = "white";
            ctx.strokeStyle = "#4A90E2";
            ctx.fillRect(handle.x - 4, handle.y - 4, 8, 8);
            ctx.strokeRect(handle.x - 4, handle.y - 4, 8, 8);
        }
    }
    ctx.restore();
}
```

**Handle hit testing (in screen space — JS only):**

```typescript
function hitTestHandle(handles: Handle[], x: number, y: number): Handle | null {
    const HIT_RADIUS = 10; // px
    for (const handle of handles) {
        if (Math.hypot(x - handle.x, y - handle.y) < HIT_RADIUS) {
            return handle;
        }
    }
    return null;
}
```

---

### 2.4 — Marching Ants Marquee Animation

The selection marquee should animate with moving dashes ("marching ants").

```typescript
let marchingAntsOffset = 0;

function animateMarquee() {
    if (selectState !== "marquee") return;
    marchingAntsOffset = (marchingAntsOffset + 0.5) % 10;
    renderMarquee();
    requestAnimationFrame(animateMarquee);
}

function renderMarquee() {
    const ctx = activeCtx;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.lineDashOffset = -marchingAntsOffset;
    ctx.strokeRect(marqueeStart.x, marqueeStart.y, marqueeW, marqueeH);
    ctx.strokeStyle = "#fff";
    ctx.lineDashOffset = -(marchingAntsOffset + 5);
    ctx.strokeRect(marqueeStart.x, marqueeStart.y, marqueeW, marqueeH);
    ctx.restore();
}
```

---

### 2.5 — Keyboard Shortcuts for Select Mode

All keyboard shortcuts must be active ONLY when the select tool is the active tool. The shortcut handler checks `activeTool === "select"` before acting.

| Key | Action | Rust call |
|-----|--------|-----------|
| `Delete` / `Backspace` | Delete selected | `engine.delete_selected()` |
| `Ctrl+D` | Duplicate selected | `engine.duplicate_selected()` |
| `ArrowUp` | Nudge up 1px | `engine.translate_selected(0, -1/scale)` |
| `ArrowDown` | Nudge down 1px | `engine.translate_selected(0, 1/scale)` |
| `ArrowLeft` | Nudge left 1px | `engine.translate_selected(-1/scale, 0)` |
| `ArrowRight` | Nudge right 1px | `engine.translate_selected(1/scale, 0)` |
| `Shift+Arrow` | Nudge 10px | Same, multiply by 10 |
| `Escape` | Deselect all | `engine.deselect_all()` |
| `Ctrl+A` | Select all | `engine.select_all()` |

Arrow nudge: convert 1px screen space to canvas space using `1 / engine.get_viewport_scale()`. Each arrow key press is its own undo entry.

**Implementation note:** Keyboard events must check `e.target` is the canvas and not a text input. If a text tool is active and focused on a text object, arrow keys should move the cursor in the text, not nudge the selection.

---

### Phase 2 Checklist for Antigravity

- [ ] `BoundingBox` struct with `union`, `contains_point`, `contains_bbox`, `center`, `expanded_by`
- [ ] `selected_ids: HashSet<u64>` on engine struct
- [ ] `stroke_bboxes: HashMap<u64, BoundingBox>` cache on engine struct
- [ ] `hit_test_point` with polygon test + polyline distance fallback
- [ ] `hit_test_marquee` with full-containment semantics
- [ ] All select/deselect methods exported via wasm_bindgen
- [ ] `begin_transform` / `commit_transform` for undo grouping
- [ ] `translate_selected`, `scale_selected`, `rotate_selected` in Rust
- [ ] `delete_selected` with `DeleteStrokes` history entry (stores full strokes)
- [ ] `duplicate_selected` with `DuplicateStrokes` history entry, returns new IDs
- [ ] JS pointer state machine with all select states
- [ ] Two-phase transform: JS visual on pointermove, Rust commit on pointerup
- [ ] `screenToCanvas` coordinate conversion used for all transform deltas
- [ ] `computeHandles` for 8 resize + 1 rotate handle
- [ ] `renderBoundingBox` on active layer
- [ ] `hitTestHandle` in screen space
- [ ] Marching ants marquee animation
- [ ] All keyboard shortcuts with correct canvas-space nudge math
- [ ] Select tool button in toolbar
- [ ] Shift+click to add/remove from selection

---

## Phase 3 — Color Change for Selected Objects

**Goal:** After selecting strokes, the user can change their color. This is the most common post-selection action and it needs to feel instant.

---

### 3.1 — Rust Engine Changes

```rust
#[wasm_bindgen]
pub fn set_selected_color(&mut self, r: f32, g: f32, b: f32, a: f32) {
    let original_colors: HashMap<u64, [f32; 4]> = self.selected_ids.iter()
        .filter_map(|id| {
            self.strokes.iter().find(|s| s.id == *id)
                .map(|s| (*id, s.color))
        })
        .collect();
    
    for stroke in self.strokes.iter_mut() {
        if self.selected_ids.contains(&stroke.id) {
            stroke.color = [r, g, b, a];
        }
    }
    
    self.history.push(HistoryEntry::RecolorStrokes {
        original_colors,
        new_color: [r, g, b, a],
    });
}

#[wasm_bindgen]
pub fn get_selected_color(&self) -> Option<Vec<f32>> {
    // Returns [r, g, b, a] if all selected strokes share the same color
    // Returns None if multiple colors are present in selection
    let colors: HashSet<String> = self.selected_ids.iter()
        .filter_map(|id| self.strokes.iter().find(|s| s.id == *id))
        .map(|s| format!("{:.3},{:.3},{:.3},{:.3}", s.color[0], s.color[1], s.color[2], s.color[3]))
        .collect();
    
    if colors.len() == 1 {
        if let Some(stroke) = self.strokes.iter().find(|s| self.selected_ids.contains(&s.id)) {
            return Some(stroke.color.to_vec());
        }
    }
    None  // Mixed colors
}
```

Add `RecolorStrokes` to `HistoryEntry`:
```rust
RecolorStrokes { 
    original_colors: HashMap<u64, [f32; 4]>, 
    new_color: [f32; 4] 
},
```

Implement undo for this: restore each stroke to its `original_colors` entry.

---

### 3.2 — Toolbar Changes

The toolbar color picker must show two states:

1. **No selection:** Shows the current pen color (used for future strokes). Unchanged behavior.
2. **Active selection:** Shows the color of the selected strokes (or a mixed-color indicator if multiple). Changing it calls `engine.set_selected_color()`.

```typescript
$: currentDisplayColor = selectedIds.length > 0 
    ? (engine.get_selected_color() ?? "mixed") 
    : activePenColor;

function onColorChange(newColor: string) {
    if (selectedIds.length > 0) {
        const [r, g, b, a] = hexToRgba(newColor);
        engine.set_selected_color(r, g, b, a);
        rerenderAll();
    } else {
        activePenColor = newColor;
    }
}
```

**Mixed color indicator:** When selection contains multiple colors, show a checkerboard or gradient swatch rather than a solid color. Clicking it still opens the picker — selecting a color from the picker applies it uniformly to all selected strokes.

**Color change must be immediate** — no debounce. The user must see the color update on the canvas in real time as they drag the color picker, not just when they release. Call `engine.set_selected_color()` on every color picker `input` event, and push the undo history entry only on `change` (release). This means temporarily suppressing undo recording during the drag:

```rust
pub fn set_selected_color_preview(&mut self, r: f32, g: f32, b: f32, a: f32) {
    // Like set_selected_color but does NOT push to history
    for stroke in self.strokes.iter_mut() {
        if self.selected_ids.contains(&stroke.id) {
            stroke.color = [r, g, b, a];
        }
    }
}

pub fn commit_color_change(&mut self, original_colors: &[u8], new_color: &[f32]) {
    // Called on picker release — pushes single undo entry
    // original_colors passed as JS Float32Array from stored pre-drag values
}
```

---

### Phase 3 Checklist for Antigravity

- [ ] `set_selected_color` in Rust with `RecolorStrokes` undo entry
- [ ] `set_selected_color_preview` in Rust (no undo push)
- [ ] `get_selected_color` in Rust (returns None for mixed)
- [ ] `RecolorStrokes` undo/redo implementation
- [ ] Toolbar shows selection color when selection is active
- [ ] Mixed color indicator swatch
- [ ] Color picker `input` event calls preview, `change` event commits
- [ ] Pre-drag original colors stored in JS, passed to `commit_color_change` on release

---

## Phase 4 — Config Struct & ML Calibration Readiness

**Goal:** All tunable drawing parameters must be in a single config struct that can be serialized, loaded from disk, and passed per-stroke. This unblocks the ML calibration system and makes the canvas feel personal.

---

### 4.1 — Rust `StrokeConfig` Struct

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
#[wasm_bindgen]
pub struct StrokeConfig {
    // Pressure simulation
    pub max_velocity: f32,       // Pixels/ms at which pressure = minimum
    pub min_pressure: f32,       // Minimum pressure value (controls minimum width)
    pub pressure_lerp: f32,      // Interpolation speed [0.0, 1.0]
    
    // Smoothing
    pub streamline_factor: f32,  // Input smoothing [0.0, 1.0]
    pub catmullrom_alpha: f32,   // Catmull-Rom parameterization [0.0 centripetal, 0.5 uniform, 1.0 chordal]
    
    // Outline shape
    pub thinning: f32,           // How much pressure affects width [-1.0, 1.0]
    pub smoothing: f32,          // Outline smoothing [0.0, 1.0]
    pub tapered_start: f32,      // Taper at stroke start [0.0, 1.0]
    pub tapered_end: f32,        // Taper at stroke end [0.0, 1.0]
    pub easing_start: EasingType,
    pub easing_end: EasingType,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EasingType {
    Linear,
    EaseIn,
    EaseOut,
    EaseInOut,
}

impl Default for StrokeConfig {
    fn default() -> Self {
        Self {
            max_velocity: 2500.0,
            min_pressure: 0.2,
            pressure_lerp: 0.15,
            streamline_factor: 0.5,
            catmullrom_alpha: 0.5,
            thinning: 0.5,
            smoothing: 0.5,
            tapered_start: 0.0,
            tapered_end: 0.0,
            easing_start: EasingType::Linear,
            easing_end: EasingType::Linear,
        }
    }
}
```

**Per-tool configs:** Each tool (pen, highlighter, marker) has its own `StrokeConfig`. The active config is selected based on the active tool.

```rust
pub struct ToolConfigs {
    pub pen: StrokeConfig,
    pub highlighter: StrokeConfig,
    pub marker: StrokeConfig,
}

impl Default for ToolConfigs {
    fn default() -> Self {
        Self {
            pen: StrokeConfig::default(),
            highlighter: StrokeConfig {
                thinning: 0.0,          // Constant width for highlighter
                min_pressure: 0.5,
                tapered_start: 0.0,
                tapered_end: 0.0,
                smoothing: 0.3,
                ..Default::default()
            },
            marker: StrokeConfig {
                thinning: 0.3,
                min_pressure: 0.4,
                ..Default::default()
            },
        }
    }
}
```

---

### 4.2 — Device Profile Storage (Python)

```python
# device_profiles.py
import json
from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger(__name__)

PROFILES_PATH = Path.home() / ".sushi" / "device_profiles.json"

def load_profile(pointer_type: str) -> Optional[dict]:
    """Load stroke config for given pointer type (mouse, pen, touch)."""
    if not PROFILES_PATH.exists():
        return None
    try:
        profiles = json.loads(PROFILES_PATH.read_text())
        return profiles.get(pointer_type)
    except Exception as e:
        log.warning("profile_load_failed", error=str(e))
        return None

def save_profile(pointer_type: str, config: dict) -> None:
    """Save stroke config for given pointer type."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = {}
        if PROFILES_PATH.exists():
            existing = json.loads(PROFILES_PATH.read_text())
        existing[pointer_type] = config
        atomic_write(PROFILES_PATH, json.dumps(existing, indent=2))
        log.info("profile_saved", pointer_type=pointer_type)
    except Exception as e:
        log.error("profile_save_failed", error=str(e))
```

---

### 4.3 — IPC Commands for Config

```python
@app.command()
async def get_stroke_config_cmd(payload: GetConfigPayload) -> dict:
    """Load config for a pointer type. Returns default if no profile exists."""
    config = load_profile(payload.pointer_type)
    if config is None:
        return ok({"config": None, "is_default": True})
    return ok({"config": config, "is_default": False})

@app.command()
async def save_stroke_config_cmd(payload: SaveConfigPayload) -> dict:
    save_profile(payload.pointer_type, payload.config)
    return ok({})
```

---

### 4.4 — Device Change Detection (Svelte)

```typescript
let lastPointerType: string = "mouse";

canvas.addEventListener("pointerdown", async (e) => {
    if (e.pointerType !== lastPointerType) {
        lastPointerType = e.pointerType;
        await onDeviceChanged(e.pointerType);
    }
    // ... rest of handler
});

async function onDeviceChanged(pointerType: string) {
    const result = await canvasInvoke<{ config: StrokeConfig | null, is_default: boolean }>(
        "get_stroke_config_cmd", { pointer_type: pointerType }
    );
    
    if (result.config) {
        engine.set_tool_configs(JSON.stringify(result.config));
    }
    
    // If no profile and calibration flag is enabled, offer calibration
    if (result.is_default && flag("ml_calibration_enabled")) {
        showCalibrationOffer(pointerType);
    }
}
```

---

### Phase 4 Checklist for Antigravity

- [ ] `StrokeConfig` struct in Rust with all fields and `Default` impl
- [ ] `EasingType` enum
- [ ] `ToolConfigs` struct with per-tool defaults
- [ ] Engine uses active tool's config for every new stroke
- [ ] `replay_stroke(raw_points, config) -> outline` WASM method (needed for ML calibration later)
- [ ] `device_profiles.py` with `load_profile` / `save_profile`
- [ ] `get_stroke_config_cmd` and `save_stroke_config_cmd` IPC commands
- [ ] Device change detection in JS pointer handler
- [ ] Config loaded from profile on device change

---

## Phase 5 — Text Tool

**Goal:** The user can click anywhere on the canvas to place a text object. Text objects are editable, selectable, resizable, and stored as structured data (not rasterized).

---

### 5.1 — Rust Data Model

Text objects live separately from strokes. They are not strokes. Add to the engine:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextObject {
    pub id: u64,
    pub x: f32,           // Canvas space, top-left
    pub y: f32,
    pub w: f32,           // Width (height auto-expands)
    pub content: String,  // Plain text (future: rich text delta)
    pub font_family: String,
    pub font_size: f32,   // In canvas-space points
    pub color: [f32; 4],  // RGBA
    pub bold: bool,
    pub italic: bool,
    pub align: TextAlign,
    
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TextAlign { Left, Center, Right }

// Engine struct additions:
pub text_objects: Vec<TextObject>,
pub selected_text_id: Option<u64>,  // The text object currently being edited
```

**New history entries:**
```rust
AddTextObject { object: TextObject },
DeleteTextObject { object: TextObject },
EditTextObject { id: u64, old_content: String, new_content: String },
TranslateTextObject { id: u64, dx: f32, dy: f32 },
```

**New WASM methods:**
```rust
pub fn add_text_object(&mut self, x: f32, y: f32) -> u64  // Returns new object ID
pub fn get_text_objects(&self) -> JsValue  // Returns Vec<TextObject> as JSON
pub fn update_text_content(&mut self, id: u64, content: &str)
pub fn update_text_style(&mut self, id: u64, style_json: &str)
pub fn delete_text_object(&mut self, id: u64)
pub fn hit_test_text_point(&self, x: f32, y: f32) -> Option<u64>
pub fn get_text_object(&self, id: u64) -> Option<JsValue>
```

---

### 5.2 — Svelte: Text Overlay Layer

Text editing cannot happen on a canvas element — it requires a real DOM input for IME support, accessibility, and cursor behavior. The text tool uses a transparent HTML overlay positioned over the canvas:

```svelte
<!-- In Canvas.svelte, above the canvas elements -->
{#if editingTextId !== null}
    <div 
        class="text-overlay-container"
        style="
            position: absolute;
            left: {textOverlayPos.x}px;
            top: {textOverlayPos.y}px;
            width: {textOverlayPos.w}px;
            min-height: 24px;
            transform: scale({viewport.scale});
            transform-origin: top left;
        "
    >
        <div
            contenteditable="true"
            bind:this={textEditorEl}
            class="text-editor-overlay"
            style="
                font-family: {activeTextStyle.fontFamily};
                font-size: {activeTextStyle.fontSize}px;
                color: {rgba(activeTextStyle.color)};
                font-weight: {activeTextStyle.bold ? 'bold' : 'normal'};
                font-style: {activeTextStyle.italic ? 'italic' : 'normal'};
                outline: 2px dashed #4A90E2;
                min-width: 100px;
                padding: 2px;
                white-space: pre-wrap;
                word-break: break-word;
            "
            oninput={onTextInput}
            onblur={onTextBlur}
            onkeydown={onTextKeydown}
        ></div>
    </div>
{/if}
```

**Positioning:** Convert the text object's canvas-space position to screen space, then position the overlay div at that screen position.

```typescript
function showTextEditor(textObj: TextObject) {
    const [sx, sy] = canvasToScreen(textObj.x, textObj.y, viewport);
    textOverlayPos = { 
        x: sx, 
        y: sy, 
        w: textObj.w * viewport.scale 
    };
    editingTextId = textObj.id;
    
    // Focus the editor after DOM update
    tick().then(() => textEditorEl?.focus());
}
```

**Text rendering on canvas (when not editing):**

When a text object is not being edited, it is rendered on the base canvas layer. JS handles the rendering — Rust returns the text object data, JS draws it.

```typescript
function renderTextObjects() {
    const objects: TextObject[] = JSON.parse(engine.get_text_objects());
    for (const obj of objects) {
        const [sx, sy] = canvasToScreen(obj.x, obj.y, viewport);
        ctx.save();
        ctx.font = `${obj.bold ? "bold " : ""}${obj.italic ? "italic " : ""}${obj.fontSize * viewport.scale}px ${obj.fontFamily}`;
        ctx.fillStyle = rgbaToString(obj.color);
        ctx.fillText(obj.content, sx, sy);
        ctx.restore();
    }
}
```

---

### 5.3 — Select Tool Integration

Text objects must be selectable by the select tool. Extend the select tool's hit testing:

```typescript
function hitTestPoint(x: number, y: number): HitResult | null {
    // First check strokes
    const strokeId = engine.hit_test_point(x, y, 5 / viewport.scale);
    if (strokeId !== null) return { type: "stroke", id: strokeId };
    
    // Then check text objects
    const textId = engine.hit_test_text_point(x, y);
    if (textId !== null) return { type: "text", id: textId };
    
    return null;
}
```

When a text object is selected:
- The bounding box renders around it
- The color picker changes its text color
- Delete key removes it
- Arrow keys nudge it

When a selected text object is double-clicked: enter text editing mode.

---

### 5.4 — Text Tool Input Flow

```
User selects text tool
  → pointermove: cursor changes to text cursor (I-beam)
  → pointerdown on empty canvas space:
      - Create new TextObject at that position via engine.add_text_object(x, y)
      - Show text editor overlay at that position
      - Focus the contenteditable div

  → pointerdown on existing text object:
      - Select it
      - Show text editor overlay

User types in the overlay div
  → onInput: engine.update_text_content(id, el.innerText)
  → Redraw base canvas (text object renders there)

User clicks away (blur event on overlay)
  → If content is empty: engine.delete_text_object(id)  [don't leave empty text objects]
  → If content has text: commit final content to engine
  → Hide overlay
  → Full rerender
```

---

### Phase 5 Checklist for Antigravity

- [ ] `TextObject` struct in Rust with all fields
- [ ] `text_objects: Vec<TextObject>` on engine struct
- [ ] All text WASM methods implemented
- [ ] Text history entries with undo/redo
- [ ] Text overlay div in `Canvas.svelte`, conditionally rendered
- [ ] `showTextEditor` / `hideTextEditor` functions
- [ ] `canvasToScreen` used for overlay positioning
- [ ] Text rendered on base canvas layer when not editing
- [ ] Text tool click on empty space creates new object
- [ ] Text tool click on existing text opens editor
- [ ] Select tool hit tests text objects
- [ ] Double-click selected text object opens editor
- [ ] Delete selected text object
- [ ] Color picker changes text color when text is selected
- [ ] Empty text objects auto-deleted on blur

---

## Phase 6 — Image Import

**Goal:** The user can drag and drop image files onto the canvas. Images become selectable, resizable objects. Images are stored in `.resources`, referenced by UUID.

---

### 6.1 — Rust Data Model

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageObject {
    pub id: u64,
    pub resource_id: String,   // UUID pointing to file in .resources
    pub x: f32,                // Canvas space
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub original_w: f32,       // Original pixel dimensions (for aspect ratio lock)
    pub original_h: f32,
    pub opacity: f32,
    
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, Value>>,
}

// Engine additions:
pub image_objects: Vec<ImageObject>,

// WASM methods:
pub fn add_image_object(&mut self, resource_id: &str, x: f32, y: f32, w: f32, h: f32, orig_w: f32, orig_h: f32) -> u64
pub fn get_image_objects(&self) -> JsValue
pub fn delete_image_object(&mut self, id: u64)
pub fn hit_test_image_point(&self, x: f32, y: f32) -> Option<u64>
```

---

### 6.2 — Python Backend: Image Resource Management

```python
# In canvas_service.py (or resource_service.py):

async def import_image_to_canvas(canvas_id: str, image_data: bytes, filename: str) -> dict:
    """Store image in .resources, return resource_id and dimensions."""
    resource_id = str(uuid4())
    
    # Determine file extension
    ext = Path(filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        raise ValueError(f"Unsupported image format: {ext}")
    
    # Store in .resources
    resource_path = get_resources_dir(canvas_id) / f"{resource_id}{ext}"
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    resource_path.write_bytes(image_data)
    
    # Get dimensions using Pillow
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(image_data))
    w, h = img.size
    
    log.info("image_imported", resource_id=resource_id, dimensions=f"{w}x{h}")
    
    return {
        "resource_id": resource_id,
        "width": w,
        "height": h,
        "path": str(resource_path)
    }
```

IPC command:
```python
@app.command()
async def import_canvas_image_cmd(payload: ImportImagePayload) -> dict:
    try:
        result = await canvas_service.import_image_to_canvas(
            payload.canvas_id,
            bytes(payload.image_data),
            payload.filename
        )
        return ok(result)
    except Exception as e:
        log.error("image_import_failed", error=str(e))
        return err("IMPORT_FAILED", str(e))
```

---

### 6.3 — Svelte: Drag-and-Drop Handler

```typescript
canvas.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer!.dropEffect = "copy";
});

canvas.addEventListener("drop", async (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer?.files ?? []);
    const imageFiles = files.filter(f => f.type.startsWith("image/"));
    
    if (imageFiles.length === 0) return;
    
    // Get drop position in canvas space
    const rect = canvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const [canvasX, canvasY] = screenToCanvas(screenX, screenY, viewport);
    
    for (const file of imageFiles) {
        await importImageFile(file, canvasX, canvasY);
    }
});

async function importImageFile(file: File, dropX: number, dropY: number) {
    const arrayBuffer = await file.arrayBuffer();
    const imageData = Array.from(new Uint8Array(arrayBuffer));
    
    const result = await canvasInvoke<ImageImportResult>("import_canvas_image_cmd", {
        canvas_id: currentCanvasId,
        image_data: imageData,
        filename: file.name
    });
    
    // Place image centered on drop point, max 400px wide in canvas space
    const maxW = 400 / viewport.scale;
    const aspectRatio = result.height / result.width;
    const w = Math.min(maxW, result.width);
    const h = w * aspectRatio;
    
    engine.add_image_object(
        result.resource_id,
        dropX - w / 2,
        dropY - h / 2,
        w, h,
        result.width, result.height
    );
    
    // Load image into browser and cache for rendering
    await loadImageForRendering(result.resource_id, result.path);
    
    rerenderAll();
}
```

**Image rendering — resource path to browser image:**

Images cannot be loaded via `file://` in a sandboxed WASM context. The Python backend must serve images through a Tauri asset protocol or convert to base64 for transport. Use an IPC command to load image bytes and render via a blob URL:

```typescript
const imageCache = new Map<string, HTMLImageElement>();

async function loadImageForRendering(resourceId: string, resourcePath: string) {
    if (imageCache.has(resourceId)) return;
    
    const result = await canvasInvoke<{ data: number[] }>("get_resource_bytes_cmd", {
        path: resourcePath
    });
    
    const blob = new Blob([new Uint8Array(result.data)]);
    const url = URL.createObjectURL(blob);
    
    const img = new Image();
    img.src = url;
    await new Promise(resolve => img.onload = resolve);
    
    imageCache.set(resourceId, img);
}

function renderImageObjects() {
    const objects: ImageObject[] = JSON.parse(engine.get_image_objects());
    for (const obj of objects) {
        const img = imageCache.get(obj.resource_id);
        if (!img) continue;
        
        const [sx, sy] = canvasToScreen(obj.x, obj.y, viewport);
        const sw = obj.w * viewport.scale;
        const sh = obj.h * viewport.scale;
        
        baseCtx.save();
        baseCtx.globalAlpha = obj.opacity;
        baseCtx.drawImage(img, sx, sy, sw, sh);
        baseCtx.restore();
    }
}
```

---

### 6.4 — Aspect Ratio Lock During Resize

When resizing an image object with a corner handle, hold Shift to maintain aspect ratio. This should be the default behavior (unlike strokes where Shift has other meanings).

```typescript
function onImageResize(handle: Handle, dx: number, dy: number, shiftHeld: boolean) {
    const obj = getImageObject(resizingId);
    const aspectRatio = obj.originalH / obj.originalW;
    
    // Compute new dimensions
    let newW = obj.w + (handle involves right edge ? dx : -dx);
    let newH = obj.h + (handle involves bottom edge ? dy : -dy);
    
    if (shiftHeld || handle.type === "nw" || handle.type === "ne" 
                   || handle.type === "se" || handle.type === "sw") {
        // Corner handles: lock aspect ratio
        newH = newW * aspectRatio;
    }
    
    engine.resize_image_object(resizingId, newW, newH);
    rerenderAll();
}
```

---

### Phase 6 Checklist for Antigravity

- [ ] `ImageObject` struct in Rust
- [ ] `image_objects: Vec<ImageObject>` on engine
- [ ] All image WASM methods
- [ ] Image history entries
- [ ] `import_image_to_canvas` in Python with Pillow for dimensions
- [ ] `import_canvas_image_cmd` IPC command
- [ ] `get_resource_bytes_cmd` IPC command
- [ ] Drag-and-drop handler on canvas element
- [ ] Image file → base64 / blob URL pipeline
- [ ] `imageCache` Map in JS
- [ ] `renderImageObjects` on base layer
- [ ] Image objects selectable by select tool
- [ ] Corner resize handles with aspect ratio lock
- [ ] Delete image object (resource file stays in `.resources`, just removes reference)
- [ ] Image opacity adjustable via select + right-click context menu

---

## Phase 7 — .jbook Format (Named Pages)

**Goal:** A `.jbook` file contains multiple named canvas pages. Each page is an independent canvas with its own strokes, text objects, and image objects. The file is a single JSON document.

---

### 7.1 — File Format Definition

```json
{
  "metadata": {
    "file_id": "uuid-v4",
    "title": "My Notebook",
    "created_at": "ISO-8601",
    "last_modified": "ISO-8601",
    "version": "1.0",
    "mode": "notebook"
  },
  "page_size": {
    "preset": "A4",
    "width_mm": 210,
    "height_mm": 297
  },
  "pages": [
    {
      "page_id": "uuid-v4",
      "name": "Page 1",
      "order": 0,
      "background": {
        "type": "none | dots | grid | lines | ruled | dotted | cornell | music_staff | isometric",
        "color": "#e0e0e0",
        "spacing": 20
      },
      "strokes": [],
      "text_objects": [],
      "image_objects": []
    }
  ],
  "resources": {
    "image-uuid-1": "relative/path/to/image.png"
  }
}
```

**Design decisions crystallized here:**

- `page_size` is a top-level field — all pages in a notebook share the same size. This covers 95% of use cases. A per-page size override can be added later if needed.
- `resources` is a top-level map — images are shared across pages without duplication.
- Each page has its own `background` settings — the user can have ruled paper for notes pages and blank pages for diagrams in the same notebook.
- `order` field on each page — allows reordering without shuffling the array.

---

### 7.2 — Rust Engine Changes

The engine currently manages a single canvas. For notebook mode, it needs to be page-aware:

**Option A (recommended):** The engine manages ONE page at a time. The JS layer loads/unloads pages by calling `engine.load_page(page_json)` and `engine.serialize_page() -> String` when switching. This keeps the Rust engine simple and avoids memory issues from holding all pages in WASM memory simultaneously.

```rust
// New WASM methods for page management:
pub fn load_page(&mut self, page_json: &str) -> Result<(), JsValue>
pub fn serialize_page(&self) -> String
pub fn get_current_page_id(&self) -> String
```

The Python backend manages the full `.jbook` structure. When the user switches pages, JS calls:
1. `engine.serialize_page()` → sends to Python to update that page in the book
2. Python saves the updated book to disk
3. JS calls `engine.load_page(new_page_json)` with the next page's data
4. Full rerender

---

### 7.3 — Python: Book Service

```python
# book_service.py

class BookService:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self._open_books: dict[str, dict] = {}  # book_id -> book data
    
    def create_book(self, title: str, page_size_preset: str = "A4") -> dict:
        book_id = str(uuid4())
        slug = slugify(title)
        filename = f"{slug}-{book_id[:8]}.jbook"
        path = self.vault_path / filename
        
        first_page_id = str(uuid4())
        book_data = {
            "metadata": {
                "file_id": book_id,
                "title": title,
                "created_at": now_iso(),
                "last_modified": now_iso(),
                "version": "1.0",
                "mode": "notebook"
            },
            "page_size": PAGE_SIZE_PRESETS[page_size_preset],
            "pages": [{
                "page_id": first_page_id,
                "name": "Page 1",
                "order": 0,
                "background": {"type": "none"},
                "strokes": [],
                "text_objects": [],
                "image_objects": []
            }],
            "resources": {}
        }
        
        atomic_write(path, json.dumps(book_data, indent=2))
        log.info("book_created", book_id=book_id, path=str(path))
        return {"book_id": book_id, "path": str(path), "first_page_id": first_page_id}
    
    def open_book(self, path: str) -> dict:
        book_data = json.loads(Path(path).read_text())
        book_data = migrate_book(book_data)
        book_id = book_data["metadata"]["file_id"]
        self._open_books[book_id] = book_data
        return {
            "book_id": book_id,
            "metadata": book_data["metadata"],
            "page_size": book_data["page_size"],
            "pages": [{"page_id": p["page_id"], "name": p["name"], "order": p["order"]} 
                      for p in sorted(book_data["pages"], key=lambda p: p["order"])]
        }
    
    def get_page(self, book_id: str, page_id: str) -> dict:
        book = self._open_books[book_id]
        page = next(p for p in book["pages"] if p["page_id"] == page_id)
        return page
    
    def update_page(self, book_id: str, page_id: str, page_data: dict) -> None:
        book = self._open_books[book_id]
        for i, page in enumerate(book["pages"]):
            if page["page_id"] == page_id:
                book["pages"][i] = page_data
                break
        book["metadata"]["last_modified"] = now_iso()
        path = self._get_book_path(book_id)
        atomic_write(path, json.dumps(book, indent=2))
    
    def add_page(self, book_id: str, after_page_id: str, name: str = None) -> dict:
        book = self._open_books[book_id]
        pages = sorted(book["pages"], key=lambda p: p["order"])
        
        after_idx = next(i for i, p in enumerate(pages) if p["page_id"] == after_page_id)
        new_order = (pages[after_idx]["order"] + 
                     (pages[after_idx + 1]["order"] if after_idx + 1 < len(pages) else pages[after_idx]["order"] + 2)) / 2
        
        new_page = {
            "page_id": str(uuid4()),
            "name": name or f"Page {len(pages) + 1}",
            "order": new_order,
            "background": {"type": "none"},
            "strokes": [],
            "text_objects": [],
            "image_objects": []
        }
        book["pages"].append(new_page)
        self.update_page.__wrapped__(self, book_id, None, None)  # just save
        return new_page
    
    def delete_page(self, book_id: str, page_id: str) -> None:
        book = self._open_books[book_id]
        if len(book["pages"]) <= 1:
            raise ValueError("Cannot delete the last page")
        book["pages"] = [p for p in book["pages"] if p["page_id"] != page_id]
        # Save
```

---

### 7.4 — Svelte: Page Strip UI

The page strip renders along the bottom (or left side) of the canvas area. It shows thumbnails of each page. The active page is highlighted.

```svelte
<div class="page-strip" role="tablist">
    {#each pages as page (page.page_id)}
        <button
            class="page-thumb"
            class:active={page.page_id === currentPageId}
            onclick={() => switchToPage(page.page_id)}
            aria-label={page.name}
        >
            {#if pageThumbnails[page.page_id]}
                <img src={pageThumbnails[page.page_id]} alt={page.name} />
            {:else}
                <div class="thumb-placeholder">{page.name}</div>
            {/if}
            <span class="page-name">{page.name}</span>
        </button>
    {/each}
    <button class="add-page-btn" onclick={addPageAfterCurrent}>+ Page</button>
</div>
```

**Page switch flow:**
```typescript
async function switchToPage(newPageId: string) {
    if (newPageId === currentPageId) return;
    
    // 1. Serialize current page state from Rust
    const currentPageData = JSON.parse(engine.serialize_page());
    
    // 2. Save to Python
    await canvasInvoke("update_page_cmd", {
        book_id: currentBookId,
        page_id: currentPageId,
        page_data: currentPageData
    });
    
    // 3. Regenerate thumbnail for current page
    await generateThumbnail(currentPageId);
    
    // 4. Load new page into Rust engine
    const newPageData = await canvasInvoke<PageData>("get_page_cmd", {
        book_id: currentBookId,
        page_id: newPageId
    });
    engine.load_page(JSON.stringify(newPageData));
    
    // 5. Load any images referenced by new page
    await preloadPageImages(newPageData);
    
    currentPageId = newPageId;
    
    // 6. Full rerender
    rerenderAll();
}
```

---

### 7.5 — Thumbnail Generation

Thumbnails are generated by rendering the canvas to an offscreen canvas and converting to a data URL:

```typescript
async function generateThumbnail(pageId: string): Promise<string> {
    const THUMB_W = 160;
    const THUMB_H = 120;
    
    const offscreen = document.createElement("canvas");
    offscreen.width = THUMB_W;
    offscreen.height = THUMB_H;
    const offCtx = offscreen.getContext("2d")!;
    
    // Scale the current canvas content to thumbnail size
    const scaleX = THUMB_W / canvas.width;
    const scaleY = THUMB_H / canvas.height;
    const scale = Math.min(scaleX, scaleY);
    
    offCtx.fillStyle = "white";
    offCtx.fillRect(0, 0, THUMB_W, THUMB_H);
    offCtx.drawImage(baseCanvas, 0, 0, canvas.width * scale, canvas.height * scale);
    
    const dataUrl = offscreen.toDataURL("image/png", 0.7);
    pageThumbnails[pageId] = dataUrl;
    return dataUrl;
}
```

---

### Phase 7 Checklist for Antigravity

- [ ] `.jbook` JSON schema as specified
- [ ] `PAGE_SIZE_PRESETS` dict in Python
- [ ] `load_page` / `serialize_page` WASM methods on engine
- [ ] `BookService` class with all CRUD methods
- [ ] IPC commands: `create_book_cmd`, `open_book_cmd`, `get_page_cmd`, `update_page_cmd`, `add_page_cmd`, `delete_page_cmd`, `reorder_page_cmd`
- [ ] `.jbook` file extension registered in `FileIndex` alongside `.jcanvas`
- [ ] Page strip UI component
- [ ] Page switch flow with serialize → save → load → rerender
- [ ] Thumbnail generation and caching
- [ ] Add/delete/rename page from page strip context menu
- [ ] Page reorder via drag in page strip
- [ ] Book mode vs canvas mode determined by `metadata.mode` field on open

---

## Phase 8 — Straight Line & Shape Recognition

**Goal:** Two distinct features — (1) Shift+draw snaps to straight lines at 45° increments, (2) holding still after completing a closed shape triggers recognition and offers to replace with a clean geometric version.

---

### 8.1 — Straight Line Mode (Shift+Draw)

**Implementation is entirely in Rust.** When `shift_held` is passed as `true` to `add_point`, the incoming point is snapped:

```rust
pub fn add_point_with_modifiers(&mut self, x: f32, y: f32, pressure: f32, 
                                 timestamp: f64, shift_held: bool) {
    let (final_x, final_y) = if shift_held && self.active_stroke_points.len() > 0 {
        let start = &self.active_stroke_points[0];
        snap_to_angle(start.x, start.y, x, y, 45.0)
    } else {
        (x, y)
    };
    
    self.add_point_internal(final_x, final_y, pressure, timestamp);
}

fn snap_to_angle(start_x: f32, start_y: f32, end_x: f32, end_y: f32, 
                  snap_degrees: f32) -> (f32, f32) {
    let dx = end_x - start_x;
    let dy = end_y - start_y;
    let angle = dy.atan2(dx);
    let snap_rad = snap_degrees.to_radians();
    let snapped_angle = (angle / snap_rad).round() * snap_rad;
    let dist = (dx * dx + dy * dy).sqrt();
    (start_x + dist * snapped_angle.cos(), start_y + dist * snapped_angle.sin())
}
```

In JS, pass `e.shiftKey` to `add_point_with_modifiers`. When shift is held during drawing, also show a visual guide: a thin line from the stroke start to the current snap point.

---

### 8.2 — Shape Recognition

Shape recognition runs in Rust (pure geometry, no ML). It is triggered 800ms after `pointerup` if the completed stroke is a closed or nearly-closed shape.

**Trigger condition:**
```rust
pub fn check_for_shape(&self, stroke_id: u64) -> Option<RecognizedShape> {
    let stroke = self.get_stroke(stroke_id)?;
    
    if stroke.points.len() < 6 {
        return None;  // Too few points
    }
    
    // Check if stroke is closed (start and end are close)
    let start = &stroke.points[0];
    let end = stroke.points.last().unwrap();
    let dist = ((end.x - start.x).powi(2) + (end.y - start.y).powi(2)).sqrt();
    let stroke_length = compute_stroke_length(&stroke.points);
    
    if dist > stroke_length * 0.15 {
        // Not closed enough — check if it's a straight line
        return try_recognize_line(&stroke.points);
    }
    
    // Try shape recognition
    try_recognize_closed_shape(&stroke.points)
}
```

**Recognized shapes:**

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RecognizedShape {
    Line { x1: f32, y1: f32, x2: f32, y2: f32 },
    Rectangle { x: f32, y: f32, w: f32, h: f32 },
    Circle { cx: f32, cy: f32, r: f32 },
    Triangle { p1: [f32; 2], p2: [f32; 2], p3: [f32; 2] },
    Arrow { x1: f32, y1: f32, x2: f32, y2: f32, head_size: f32 },
}
```

**Recognition algorithm (per shape):**

*Line:* Compute the residual of fitting a straight line to all points. If residual/length < 0.08, it's a line.

*Rectangle:* Find the convex hull. If it has 4 corners (within tolerance), check if opposite sides are parallel and angles are close to 90°.

*Circle:* Fit a circle using least-squares. If the mean distance from all points to the fitted circle / radius < 0.12, it's a circle.

*Triangle:* Convex hull has 3 corners. Verify angles sum close to 180°.

**The user interaction:**

When a shape is recognized, show a non-blocking toast at the bottom of the screen: `"Rectangle detected — Replace?" [Keep] [Replace]`. Auto-dismiss after 3 seconds with "Keep" behavior.

```typescript
let pendingShapeTimer: number | null = null;

canvas.addEventListener("pointerup", async () => {
    commitStroke();
    
    const strokeId = engine.get_last_committed_stroke_id();
    
    // 800ms delay before checking
    pendingShapeTimer = setTimeout(async () => {
        const recognized = engine.check_for_shape(strokeId);
        if (recognized) {
            showShapeToast(recognized, strokeId);
        }
    }, 800);
});

function showShapeToast(shape: RecognizedShape, strokeId: number) {
    // Show toast with Replace/Keep buttons
    // If Replace: engine.replace_stroke_with_shape(strokeId, shape) → rerenderAll
    // If Keep or timeout: do nothing, stroke stays as-is
    toast.show({
        message: `${getShapeName(shape)} detected — Replace?`,
        actions: [
            { label: "Keep", handler: () => {} },
            { label: "Replace", handler: () => replaceWithShape(strokeId, shape) }
        ],
        timeout: 3000,
        onTimeout: () => {}  // Keep
    });
}
```

**Rust — `replace_stroke_with_shape`:**

Replace the freehand stroke with a clean geometric version. The replacement is itself a stroke (outline polygon), not a special shape type. This means all existing selection/erase/undo logic works on it unchanged.

```rust
pub fn replace_stroke_with_shape(&mut self, stroke_id: u64, shape_json: &str) -> Result<(), JsValue> {
    let shape: RecognizedShape = serde_json::from_str(shape_json)?;
    
    // Find the original stroke to preserve color, width, tool settings
    let original = self.get_stroke(stroke_id).cloned().ok_or("Stroke not found")?;
    
    // Generate clean outline for the shape
    let new_outline = shape_to_outline(&shape, original.width);
    
    // Replace stroke outline in place (preserves id, color, tool)
    if let Some(stroke) = self.strokes.iter_mut().find(|s| s.id == stroke_id) {
        let old_outline = stroke.outline.clone();
        stroke.outline = new_outline;
        stroke.points.clear();  // Shape strokes have no raw points
        
        self.history.push(HistoryEntry::ReplaceStrokeWithShape { 
            stroke_id, old_outline 
        });
    }
    
    Ok(())
}
```

---

### Phase 8 Checklist for Antigravity

- [ ] `add_point_with_modifiers` in Rust accepting `shift_held: bool`
- [ ] `snap_to_angle` function in Rust
- [ ] JS passes `e.shiftKey` to Rust on every point
- [ ] Shift guide line visual on active layer during drawing
- [ ] `RecognizedShape` enum in Rust
- [ ] `check_for_shape` with line, rectangle, circle, triangle recognizers
- [ ] 800ms timer after pointerup, cancelled if new stroke started
- [ ] Shape toast component with Replace/Keep/3s timeout
- [ ] `replace_stroke_with_shape` in Rust with undo entry
- [ ] `shape_to_outline` for each shape type

---

## Phase 9 — Background Patterns

**Goal:** Canvas background can be set to dots, grid, lines, ruled, Cornell notes, isometric, music staff, or none. Background is rendered in JS using canvas 2D, never stored as part of the stroke data.

---

### 9.1 — Data Model

Background config lives in the canvas/page metadata, not in stroke data:

```typescript
interface BackgroundConfig {
    type: "none" | "dots" | "grid" | "lines" | "ruled" | "dotted" | 
          "cornell" | "music_staff" | "isometric" | "custom";
    color: string;      // Hex color for pattern lines/dots
    spacing: number;    // Base spacing in canvas-space units
    tile_ref?: string;  // resource_id for custom SVG/image tile
}
```

In `.jcanvas`:
```json
"background": {
    "type": "dots",
    "color": "#d0d0d0",
    "spacing": 20
}
```

---

### 9.2 — Rendering (JS Only)

Background is rendered on a third canvas layer behind the base canvas. It is re-rendered whenever the viewport changes (pan or zoom).

```typescript
function renderBackground(config: BackgroundConfig, viewport: Viewport) {
    bgCtx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (config.type === "none") return;
    
    bgCtx.save();
    bgCtx.strokeStyle = config.color;
    bgCtx.fillStyle = config.color;
    
    const spacing = config.spacing * viewport.scale;
    
    // Compute the visible canvas range in canvas-space coordinates
    const [startX, startY] = screenToCanvas(0, 0, viewport);
    const [endX, endY] = screenToCanvas(canvas.width, canvas.height, viewport);
    
    // Snap start to grid
    const snapX = Math.floor(startX / config.spacing) * config.spacing;
    const snapY = Math.floor(startY / config.spacing) * config.spacing;
    
    switch (config.type) {
        case "dots":
            renderDots(bgCtx, snapX, snapY, endX, endY, config, viewport);
            break;
        case "grid":
            renderGrid(bgCtx, snapX, snapY, endX, endY, config, viewport);
            break;
        case "lines":
            renderLines(bgCtx, snapX, snapY, endX, endY, config, viewport);
            break;
        case "isometric":
            renderIsometric(bgCtx, snapX, snapY, endX, endY, config, viewport);
            break;
        // ... etc
    }
    
    bgCtx.restore();
}
```

**Dots implementation:**
```typescript
function renderDots(ctx, startX, startY, endX, endY, config, viewport) {
    const dotRadius = Math.max(0.5, 1.0 * viewport.scale);
    
    for (let cx = startX; cx <= endX; cx += config.spacing) {
        for (let cy = startY; cy <= endY; cy += config.spacing) {
            const [sx, sy] = canvasToScreen(cx, cy, viewport);
            ctx.beginPath();
            ctx.arc(sx, sy, dotRadius, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}
```

**Performance note:** Only render dots/lines that are visible in the current viewport. The `startX/startY` snapping ensures this. For large spacing values this is fast. For very small spacing (< 5px per dot at current zoom), skip rendering below a minimum threshold to avoid performance degradation.

```typescript
// Don't render if spacing would be less than 4px on screen
if (spacing < 4) return;
```

---

### 9.3 — Three Canvas Layer Architecture

Update `Canvas.svelte` to have three canvas elements:

```svelte
<div class="canvas-container" style="position: relative; width: 100%; height: 100%;">
    <!-- Layer 0: Background pattern (behind everything) -->
    <canvas bind:this={bgCanvas} 
            style="position: absolute; top: 0; left: 0; pointer-events: none;"/>
    
    <!-- Layer 1: Base layer (committed strokes, text, images) -->
    <canvas bind:this={baseCanvas}
            style="position: absolute; top: 0; left: 0; pointer-events: none;"/>
    
    <!-- Layer 2: Active layer (in-progress stroke, selection UI) -->
    <!-- This layer captures all pointer events -->
    <canvas bind:this={activeCanvas}
            style="position: absolute; top: 0; left: 0;"
            onpointerdown={onPointerDown}
            onpointermove={onPointerMove}
            onpointerup={onPointerUp}
            onpointercancel={onPointerCancel}/>
</div>
```

`renderBackground()` draws to `bgCanvas`. Background is re-rendered on viewport change. It does NOT re-render on every stroke — only on pan/zoom.

---

### 9.4 — Toolbar: Background Picker

A background picker panel (accessible from toolbar or right-click context menu):

```svelte
<div class="background-picker-panel">
    <div class="pattern-grid">
        {#each PATTERNS as pattern}
            <button 
                class="pattern-option" 
                class:active={bgConfig.type === pattern.type}
                onclick={() => setBackground(pattern.type)}
                title={pattern.label}
            >
                <canvas width="40" height="40" use:renderPatternPreview={pattern} />
                <span>{pattern.label}</span>
            </button>
        {/each}
    </div>
    <label>Color
        <input type="color" bind:value={bgConfig.color} oninput={onBgColorChange}/>
    </label>
    <label>Spacing
        <input type="range" min="10" max="60" bind:value={bgConfig.spacing} oninput={onBgSpacingChange}/>
    </label>
</div>
```

---

### Phase 9 Checklist for Antigravity

- [ ] `BackgroundConfig` interface in TypeScript
- [ ] Three-layer canvas architecture in `Canvas.svelte`
- [ ] `renderBackground` function
- [ ] Dot, grid, line, ruled, isometric, music staff renderers
- [ ] Minimum spacing threshold (< 4px → skip render)
- [ ] Background re-renders on viewport change, not on stroke
- [ ] Background config stored in `.jcanvas` metadata
- [ ] Background picker UI panel
- [ ] Color and spacing controls update live
- [ ] Background not included in stroke export SVG by default

---

## Phase 10 — Gesture & Input Expansion

**Goal:** Complete the input layer to handle all edge cases and hardware inputs correctly.

---

### 10.1 — Palm Rejection

For stylus users, finger touches while the stylus is active should be ignored. This prevents accidental palm smears.

```typescript
let stylusActive = false;
const PALM_REJECT_TIMEOUT = 500; // ms after stylus up before fingers accepted

canvas.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "pen") {
        stylusActive = true;
        // Process normally
    } else if (e.pointerType === "touch") {
        if (stylusActive) {
            e.preventDefault(); // Palm rejection
            return;
        }
        // Process as finger (pan/pinch only)
    }
});

canvas.addEventListener("pointerup", (e) => {
    if (e.pointerType === "pen") {
        setTimeout(() => { stylusActive = false; }, PALM_REJECT_TIMEOUT);
    }
});
```

---

### 10.2 — Stylus Button Support

Many styluses have a barrel button (secondary button) and an eraser end. Handle these:

```typescript
canvas.addEventListener("pointerdown", (e) => {
    // Check for stylus eraser end
    if (e.pointerType === "pen" && e.buttons === 32) {
        // 32 = eraser button bit
        activateTemporaryEraser();
        return;
    }
    
    // Check for stylus barrel button (button 2)
    if (e.pointerType === "pen" && e.buttons === 2) {
        // Barrel button: context menu or pan mode
        activateTemporaryPan();
        return;
    }
});

canvas.addEventListener("pointerup", (e) => {
    deactivateTemporaryTool();
});
```

---

### 10.3 — Coalesced Events Pressure Interpolation

Some devices (especially touchscreens) report pressure as 0 for coalesced events. Interpolate pressure between the bookend events:

```typescript
function processCoalescedEvents(e: PointerEvent) {
    const coalesced = e.getCoalescedEvents();
    const events = coalesced.length > 0 ? coalesced : [e];
    
    // Find pressure values at start and end
    const startPressure = events[0].pressure;
    const endPressure = e.pressure;
    
    events.forEach((coalescedEvent, i) => {
        const t = i / Math.max(events.length - 1, 1);
        const pressure = coalescedEvent.pressure > 0 
            ? coalescedEvent.pressure 
            : lerp(startPressure, endPressure, t);  // Interpolate if zero
        
        const [cx, cy] = screenToCanvas(coalescedEvent.clientX - rect.left, 
                                         coalescedEvent.clientY - rect.top, viewport);
        engine.add_point_with_modifiers(cx, cy, pressure, coalescedEvent.timeStamp, 
                                         isShiftHeld);
    });
}
```

---

### Phase 10 Checklist for Antigravity

- [ ] Palm rejection: finger touch ignored when stylus is active
- [ ] Stylus eraser end (`e.buttons === 32`) activates temporary eraser
- [ ] Stylus barrel button activates temporary pan
- [ ] Coalesced events pressure interpolation for zero-pressure coalesced events
- [ ] `cancelActiveDraw` called when unexpected gesture occurs (3+ fingers)
- [ ] `pointercancel` handler cleans up all in-flight state

---

## Phase 11 — Canvas-as-a-Block Integration

**Goal:** The canvas engine is embedded into Sushi Notes as a block type. This is the first integration phase — a working `CanvasBlock.svelte` that creates, saves, loads, and thumbnails canvas blocks.

---

### 11.1 — Build Integration

**Move `canvas-engine` crate into Sushi Notes workspace:**

Root `Cargo.toml`:
```toml
[workspace]
members = [
    "src-tauri",
    "canvas-engine",
]
```

`vite.config.ts` in Sushi Notes:
```typescript
import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
    resolve: {
        alias: {
            '$canvas-engine': resolve('./canvas-engine/pkg')
        }
    },
    // ... rest of config
})
```

The `canvas-engine/pkg/` directory is the wasm-pack output. Add to `.gitignore` — it's a build artifact.

Build command additions to `package.json`:
```json
{
    "scripts": {
        "build:wasm": "wasm-pack build canvas-engine --target web --out-dir canvas-engine/pkg",
        "build": "npm run build:wasm && vite build",
        "dev": "npm run build:wasm && vite dev"
    }
}
```

---

### 11.2 — CanvasBlock.svelte Component Contract

File: `src/lib/components/editor/CanvasBlock.svelte`

```typescript
// Props (must follow the exact same contract as all other block components)
interface Props {
    block: CanvasBlockData;
    noteId: string;
    isFocused: boolean;
}

// Events
interface Events {
    change: CanvasBlockData;   // Emitted when block data changes (triggers note save)
    delete: void;              // Emitted when block requests removal
    focus: void;               // Emitted when canvas receives focus
    blur: void;                // Emitted when canvas loses focus
}
```

**Block states:**

1. **Collapsed (not focused):** Renders a thumbnail image from `block.data.thumbnail_ref`. Shows page dimensions. Has a "+Canvas" overlay hint.
2. **Loading:** Spinner while WASM loads and canvas data is fetched from Python.
3. **Expanded (focused):** Full canvas editor with toolbar. Height is fixed to page dimensions (respects the A4 size constraint, not infinite).
4. **Saving:** Brief visual indicator while thumbnail is being regenerated.

**Focus/blur handling:**

```typescript
let isFocused = false;

function onCanvasClick() {
    if (!isFocused) {
        isFocused = true;
        dispatch("focus");
        loadCanvas();
    }
}

async function onBlur() {
    if (!isFocused) return;
    isFocused = false;
    
    // Save canvas state
    await saveCanvasBlock();
    
    dispatch("blur");
    dispatch("change", updatedBlockData);
}
```

---

### 11.3 — Canvas Save Flow

```typescript
async function saveCanvasBlock() {
    // 1. Serialize current canvas state from Rust
    const canvasData = engine.serialize();
    
    // 2. Generate thumbnail
    const thumbnailDataUrl = await generateThumbnail();
    
    // 3. Send to Python
    const result = await canvasInvoke<SaveCanvasResult>("save_canvas_block_cmd", {
        note_id: noteId,
        block_id: block.block_id,
        canvas_data: canvasData,
        thumbnail_data_url: thumbnailDataUrl,
        canvas_ref: block.data.canvas_ref  // UUID
    });
    
    // 4. Update block data
    block = {
        ...block,
        data: {
            ...block.data,
            thumbnail_ref: result.thumbnail_ref,
            thumbnail_version: result.thumbnail_version
        }
    };
}
```

**Python — `save_canvas_block_cmd`:**

```python
@app.command()
async def save_canvas_block_cmd(payload: SaveCanvasBlockPayload) -> dict:
    try:
        # Get resources dir for this note
        note_path = vault_service.get_note_path(payload.note_id)
        resources_dir = note_path.parent / ".resources"
        resources_dir.mkdir(exist_ok=True)
        
        # Save canvas data
        canvas_path = resources_dir / payload.canvas_ref
        atomic_write(canvas_path, payload.canvas_data)
        
        # Save thumbnail
        thumb_path = resources_dir / f"{Path(payload.canvas_ref).stem}-thumb.png"
        save_data_url_as_png(payload.thumbnail_data_url, thumb_path)
        
        # Get new thumbnail version
        thumb_version = get_resource_version(thumb_path)
        
        log.info("canvas_block_saved", 
                 note_id=payload.note_id, 
                 block_id=payload.block_id)
        
        return ok({
            "thumbnail_ref": thumb_path.name,
            "thumbnail_version": thumb_version
        })
    except Exception as e:
        log.error("canvas_block_save_failed", error=str(e))
        return err("SAVE_FAILED", str(e))
```

---

### 11.4 — Keyboard Shortcut Scoping

Canvas keyboard shortcuts (Ctrl+Z, Delete, etc.) must activate only when the canvas block is focused. The note editor's shortcuts must be suppressed when the canvas is focused.

```typescript
// In CanvasBlock.svelte:
function onKeydown(e: KeyboardEvent) {
    if (!isFocused) return;
    
    e.stopPropagation();  // Prevent note editor from receiving this
    
    if (e.ctrlKey && e.key === "z") {
        engine.undo();
        rerenderAll();
    }
    // ... etc
}

// The canvas element captures key events when focused:
// <canvas tabindex="0" onkeydown={onKeydown} />
```

In `MainArea.svelte`, check `!isCanvasFocused` before processing note-level shortcuts.

---

### 11.5 — WASM Loading Strategy

WASM loading is async and non-trivial. It must not block the note editor rendering. Strategy:

```typescript
// In a module-level singleton:
let enginePromise: Promise<CanvasEngine> | null = null;

export function getEngine(): Promise<CanvasEngine> {
    if (!enginePromise) {
        enginePromise = initCanvasEngine();
    }
    return enginePromise;
}

async function initCanvasEngine(): Promise<CanvasEngine> {
    const wasm = await import("$canvas-engine");
    await wasm.default();  // Initialize WASM
    return new wasm.CanvasEngine();
}
```

Each `CanvasBlock` component calls `getEngine()` — if the engine is already loaded, it resolves immediately. If multiple canvas blocks are on the same note, they share one engine instance but each has its own canvas state loaded via `engine.load_page()`.

**Important:** Canvas blocks cannot share a single engine instance if the engine has global state (like viewport, undo history). Either: (a) each canvas block instantiates its own engine (expensive), or (b) the engine supports multiple independent "sessions." Recommended: one engine per block, lazy-loaded only when the block is focused. Unfocused blocks just show thumbnails.

---

### Phase 11 Checklist for Antigravity

- [ ] `canvas-engine` added to Sushi Notes workspace `Cargo.toml`
- [ ] `vite.config.ts` alias for `$canvas-engine`
- [ ] `build:wasm` npm script
- [ ] `CanvasBlock.svelte` with collapsed/loading/expanded/saving states
- [ ] Thumbnail display when collapsed
- [ ] Focus click expands to full canvas
- [ ] Blur collapses and triggers save
- [ ] `save_canvas_block_cmd` Python handler
- [ ] `load_canvas_block_cmd` Python handler
- [ ] Thumbnail generation on blur
- [ ] `save_data_url_as_png` utility in Python
- [ ] Keyboard shortcut scoping: canvas captures keys when focused
- [ ] Engine lazy-loading singleton
- [ ] `.resources` folder creation per note

---

## Phase 12 — Infinite Canvas as Vault File

**Goal:** `.jcanvas` and `.jbook` files appear in the Sushi Notes sidebar as first-class vault items. Opening one shows a full-screen canvas view.

---

### 12.1 — FileIndex Changes

Add to the `FileIndex` SQLite schema:

```sql
CREATE TABLE IF NOT EXISTS canvas_files (
    file_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- 'jcanvas' or 'jbook'
    created_at TEXT,
    last_modified TEXT,
    last_known_path TEXT
);
```

`VaultService.rebuild_index()` must scan for `.jcanvas` and `.jbook` files alongside `.jnote` files.

---

### 12.2 — IPC Commands

```python
@app.command()
async def create_canvas_file_cmd(payload: CreateCanvasPayload) -> dict:
    # Creates a new .jcanvas or .jbook file
    ...

@app.command()
async def open_canvas_file_cmd(payload: OpenCanvasPayload) -> dict:
    # Loads and returns canvas data
    ...

@app.command()  
async def save_canvas_file_cmd(payload: SaveCanvasPayload) -> dict:
    # Saves canvas data atomically
    ...

@app.command()
async def delete_canvas_file_cmd(payload: DeleteCanvasPayload) -> dict:
    # Moves to trash, updates FileIndex
    ...
```

---

### 12.3 — Main Area Router

`MainArea.svelte` currently always renders the note editor. Add routing:

```typescript
type MainAreaView = 
    | { type: "note"; noteId: string }
    | { type: "canvas"; canvasId: string; filePath: string }
    | { type: "book"; bookId: string; filePath: string }
    | { type: "empty" }

let currentView: MainAreaView = { type: "empty" };

// When a file is opened from the sidebar:
function openFile(file: VaultFile) {
    if (file.type === "jnote") {
        currentView = { type: "note", noteId: file.id };
    } else if (file.type === "jcanvas") {
        currentView = { type: "canvas", canvasId: file.id, filePath: file.path };
    } else if (file.type === "jbook") {
        currentView = { type: "book", bookId: file.id, filePath: file.path };
    }
}
```

```svelte
{#if currentView.type === "note"}
    <NoteEditor noteId={currentView.noteId} />
{:else if currentView.type === "canvas"}
    <InfiniteCanvas canvasId={currentView.canvasId} filePath={currentView.filePath} />
{:else if currentView.type === "book"}
    <NotebookCanvas bookId={currentView.bookId} filePath={currentView.filePath} />
{:else}
    <EmptyState />
{/if}
```

---

### Phase 12 Checklist for Antigravity

- [ ] `canvas_files` table in FileIndex
- [ ] `rebuild_index` scans for `.jcanvas` and `.jbook`
- [ ] All canvas file CRUD IPC commands
- [ ] `VaultWatcher` detects changes to canvas files, fires tree-changed events
- [ ] Sidebar renders canvas/book files with distinct icons
- [ ] Main area router handles canvas and book views
- [ ] `InfiniteCanvas.svelte` component (full-screen, pan/zoom)
- [ ] `NotebookCanvas.svelte` component (page strip + fixed page view)
- [ ] Auto-save on a timer (every 30s) for open canvas files
- [ ] "New Canvas" / "New Notebook" in sidebar context menu

---

## Phase 13 — PDF Annotation Canvas

**Goal:** Sushi can open PDFs. Each PDF page has a finite canvas annotation layer on top. Users can draw, highlight, and annotate directly on the PDF.

---

### 13.1 — Architecture Overview

Three layers stacked with `position: absolute`:

```
Layer 3 — Sushi Canvas WASM (finite mode, page-locked)
  Captures pointer events when draw/highlight mode is active
  
Layer 2 — Text Selection (Hit testing)
  Per-character bbox map from pdfium-render
  Captures pointer events when text selection mode is active
  
Layer 1 — PDF Render (pdfium-render WASM)
  Renders PDF page as bitmap
  pointer-events: none (never captures events)
```

Layer routing is CSS-only. No JavaScript event routing:
```typescript
function setActiveLayer(mode: "draw" | "text_select" | "cursor") {
    layer3Canvas.style.pointerEvents = mode === "draw" ? "auto" : "none";
    layer2El.style.pointerEvents = mode === "text_select" ? "auto" : "none";
}
```

---

### 13.2 — pdfium-render Integration

```python
# pdf_service.py

class PDFService:
    def __init__(self):
        self._open_pdfs: dict[str, PDFDocument] = {}  # pdf_id -> document
    
    def open_pdf(self, path: str) -> dict:
        """Open PDF and return metadata. Pages rendered on demand."""
        pdf_id = self._get_or_assign_uuid(path)
        doc = load_pdfium(Path(path))
        self._open_pdfs[pdf_id] = doc
        
        return {
            "pdf_id": pdf_id,
            "page_count": len(doc.pages),
            "title": doc.metadata.get("Title", Path(path).stem)
        }
    
    def render_page(self, pdf_id: str, page_num: int, scale: float) -> dict:
        """Render a page as PNG bytes at the given scale."""
        doc = self._open_pdfs[pdf_id]
        page = doc.pages[page_num]
        
        # Render to bitmap
        bitmap = page.render(scale=scale)
        png_bytes = bitmap.to_png()
        
        # Extract character bboxes
        text_layer = page.get_text_layer()
        chars = [
            {"char": c.char, "x": c.bbox.x, "y": c.bbox.y, 
             "w": c.bbox.w, "h": c.bbox.h}
            for c in text_layer.chars
        ]
        
        return {
            "image_data": list(png_bytes),
            "page_width_pts": page.width,
            "page_height_pts": page.height,
            "chars": chars
        }
```

IPC commands:
```python
@app.command()
async def open_pdf_cmd(payload): ...

@app.command()
async def render_pdf_page_cmd(payload): ...

@app.command()
async def save_pdf_annotation_cmd(payload): ...

@app.command()
async def load_pdf_annotation_cmd(payload): ...
```

---

### 13.3 — PDF UUID System

On first import of a PDF:
1. Python computes a UUID and stores it in a `pdf_registry.json` at vault root:
   ```json
   {
     "pdf-uuid-1": {
       "last_known_path": "relative/path/to/paper.pdf",
       "imported_at": "ISO-8601"
     }
   }
   ```
2. A `.resources/pdf-annotations/pdf-uuid-1/` directory is created.
3. Annotation files: `page-0.jcanvas`, `page-1.jcanvas`, etc., created on first annotation.

UUID is path-stable — if the PDF moves within the vault, the UUID follows via `VaultWatcher`.

---

### 13.4 — Finite Canvas Mode

The canvas engine needs a "finite mode" where the viewport cannot scroll outside the page boundary:

```rust
pub enum CanvasMode {
    Infinite,
    Finite { width: f32, height: f32 },  // In canvas-space (PDF points)
}

// In viewport.rs:
pub fn clamp_viewport_to_finite(&mut self, mode: &CanvasMode) {
    if let CanvasMode::Finite { width, height } = mode {
        // Prevent panning outside page bounds
        // Prevent zooming out below "fit page" level
        ...
    }
}
```

The finite canvas still supports pan and zoom within the page bounds. The page boundary is drawn as a subtle shadow/border.

---

### 13.5 — Coordinate System

Critical: all annotation stroke coordinates are stored in PDF user-space (72 points per inch). They are NOT stored in screen pixels. This makes them zoom-independent.

```typescript
// Convert screen pointer event to PDF user-space coordinates
function screenToPDFSpace(screenX: number, screenY: number): [number, number] {
    // 1. Convert screen to canvas-space (handles pan/zoom)
    const [canvasX, canvasY] = screenToCanvas(screenX, screenY, viewport);
    
    // 2. Canvas-space IS PDF user-space in finite mode
    // (The engine's coordinate space is set up to match PDF points)
    return [canvasX, canvasY];
}
```

The viewport is initialized so that 1 canvas unit = 1 PDF point. Zoom changes the scale but not the coordinate system.

---

### 13.6 — Text Selection in PDF

```typescript
interface CharBbox {
    char: string;
    x: number; y: number; w: number; h: number;  // PDF user-space
}

let charBboxes: CharBbox[] = [];  // Populated when page loads
let selection: CharBbox[] = [];

// Layer 2 pointer handler (text selection mode):
function onTextSelectionPointerDown(e: PointerEvent) {
    selectionStart = pointerToPDFSpace(e);
    selection = [];
}

function onTextSelectionPointerMove(e: PointerEvent) {
    const current = pointerToPDFSpace(e);
    const selRect = rectFromPoints(selectionStart, current);
    
    // Hit test all chars against selection rect
    selection = charBboxes.filter(c => rectsOverlap(selRect, c));
    
    renderSelectionHighlight(selection);
}

function onTextSelectionPointerUp(e: PointerEvent) {
    if (selection.length > 0) {
        showTextSelectionMenu(selection);
    }
}
```

**Text selection menu actions:**
- Copy text
- Highlight (creates a highlighter stroke on Layer 3)
- Create quote block in active note

---

### Phase 13 Checklist for Antigravity

- [ ] `pdfium-render` crate added to workspace
- [ ] `PDFService` with open/render/close
- [ ] `pdf_registry.json` UUID assignment system
- [ ] All PDF IPC commands
- [ ] Three-layer PDF viewer component
- [ ] CSS `pointer-events` routing between layers
- [ ] `CanvasMode::Finite` in Rust with viewport clamping
- [ ] PDF coordinate system: 1 canvas unit = 1 PDF point
- [ ] `render_pdf_page_cmd` returns PNG bytes + char bboxes
- [ ] Text selection pointer handler on Layer 2
- [ ] Selection highlight rendered as semi-transparent overlay
- [ ] "Highlight" action creates a stroke on Layer 3
- [ ] Annotation saves/loads from `page-N.jcanvas` sidecar
- [ ] PDF file appears in vault sidebar with PDF icon
- [ ] Page navigation (keyboard + thumbnail strip)

---

## Phase 14 — Canvas Snippets & Deep Linking

**Goal:** A user can select a rectangular region of any canvas (block, infinite canvas, or PDF page) and embed it as a live-linked snapshot block in a note.

---

### 14.1 — Region Select Tool

Add "Region Select" to the canvas tool palette. It is only available in non-drawing modes (when a note is also visible).

```typescript
// Region select state
let regionStart: [number, number] | null = null;
let regionRect: { x: number; y: number; w: number; h: number } | null = null;

function onRegionPointerDown(e: PointerEvent) {
    regionStart = screenToCanvas(e.clientX - rect.left, e.clientY - rect.top, viewport);
    regionRect = null;
}

function onRegionPointerMove(e: PointerEvent) {
    if (!regionStart) return;
    const current = screenToCanvas(...);
    regionRect = {
        x: Math.min(regionStart[0], current[0]),
        y: Math.min(regionStart[1], current[1]),
        w: Math.abs(current[0] - regionStart[0]),
        h: Math.abs(current[1] - regionStart[1])
    };
    renderRegionSelector(regionRect);
}

function onRegionPointerUp(e: PointerEvent) {
    if (regionRect && regionRect.w > 10 && regionRect.h > 10) {
        showRegionActionMenu(regionRect);
    }
    regionStart = null;
}
```

---

### 14.2 — Snapshot Generation

When "Create Snippet" is selected from the region action menu:

```typescript
async function createSnippet(region: RegionRect) {
    // 1. Render just this region to an offscreen canvas
    const snapshotDataUrl = renderRegionToDataUrl(region, viewport);
    
    // 2. Send to Python to store in .resources
    const result = await canvasInvoke<SnippetResult>("create_canvas_snippet_cmd", {
        source_type: currentSourceType,  // "canvas_block" | "infinite_canvas" | "pdf_annotation"
        source_id: currentCanvasId,
        source_block_id: currentBlockId ?? null,
        source_page: currentPage ?? null,
        region: region,
        snapshot_data_url: snapshotDataUrl,
        target_note_id: activeNoteId,
        update_mode: "notify"
    });
    
    // 3. Python inserts a canvas-snippet block into the target note
    // The note editor picks this up via filesystem watcher
}
```

---

### 14.3 — Python: Snippet Handler

```python
@app.command()
async def create_canvas_snippet_cmd(payload: CreateSnippetPayload) -> dict:
    # 1. Generate snippet UUID
    snippet_id = str(uuid4())
    
    # 2. Save snapshot image to note's .resources
    note_path = vault_service.get_note_path(payload.target_note_id)
    resources_dir = note_path.parent / ".resources"
    snapshot_path = resources_dir / f"snippet-{snippet_id}.png"
    save_data_url_as_png(payload.snapshot_data_url, snapshot_path)
    
    # 3. Create the canvas-snippet block
    snippet_block = {
        "block_id": generate_short_id(),
        "type": "canvas-snippet",
        "data": {
            "source_type": payload.source_type,
            "source_id": payload.source_id,
            "source_block_id": payload.source_block_id,
            "source_page": payload.source_page,
            "region": payload.region,
            "snapshot_ref": f"snippet-{snippet_id}.png",
            "snapshot_version": 1,
            "update_mode": payload.update_mode
        },
        "version": "1.0",
        "tags": [],
        "backlinks": [{"type": "canvas_region_ref", "target_id": payload.source_id}]
    }
    
    # 4. Insert block into note
    vault_service.append_block_to_note(payload.target_note_id, snippet_block)
    
    return ok({"snippet_block_id": snippet_block["block_id"]})
```

---

### 14.4 — CanvasSnippetBlock.svelte

```svelte
<div class="canvas-snippet-block">
    <div class="snippet-image-container" onclick={onSnippetClick}>
        <img src={snapshotUrl} alt="Canvas snippet" />
        {#if data.update_mode === "notify" && isStale}
            <div class="stale-badge" title="Source has changed — click to refresh">
                ↻
            </div>
        {/if}
        <div class="source-indicator">
            {sourceIcon} {sourceName}
        </div>
    </div>
</div>

<script>
async function onSnippetClick() {
    // Navigate to source
    await canvasInvoke("navigate_to_canvas_region_cmd", {
        source_type: block.data.source_type,
        source_id: block.data.source_id,
        source_block_id: block.data.source_block_id,
        source_page: block.data.source_page,
        region: block.data.region
    });
}
</script>
```

---

### 14.5 — Change Detection & Stale Snippets

After every canvas save, Python checks if any snippets reference this canvas:

```python
async def on_canvas_saved(canvas_id: str) -> None:
    # Find all snippet blocks that reference this canvas
    referencing_snippets = vault_service.find_snippets_by_source(canvas_id)
    
    for snippet in referencing_snippets:
        if snippet["data"]["update_mode"] == "auto_silent":
            await refresh_snippet(snippet)
        elif snippet["data"]["update_mode"] == "notify":
            await mark_snippet_stale(snippet)
        # "manual" mode: do nothing
```

---

### Phase 14 Checklist for Antigravity

- [ ] Region select tool in canvas toolbar
- [ ] Region selector rendering (dashed rect + crosshair)
- [ ] Region action menu (Create Snippet, Copy as Image)
- [ ] `renderRegionToDataUrl` — offscreen canvas render of region
- [ ] `create_canvas_snippet_cmd` Python handler
- [ ] `find_snippets_by_source` in VaultService
- [ ] `on_canvas_saved` hook that checks for stale snippets
- [ ] `CanvasSnippetBlock.svelte` with image + stale badge
- [ ] Click navigates to source
- [ ] Source deleted → broken link dialog (keep as image / delete)
- [ ] Deep link navigation: `navigate_to_canvas_region_cmd`

---

## Phase 15 — ML Calibration System

**Goal:** Per-device, per-user stroke parameter optimization via preference-based Bayesian optimization. After ~20 A/B comparisons, the system converges on optimal parameters.

---

### 15.1 — Rust: Replay API

Add a pure function that takes raw input points and a config, and returns the outline. This is the key API the calibration system needs:

```rust
#[wasm_bindgen]
pub fn replay_stroke(raw_points_json: &str, config_json: &str) -> Result<JsValue, JsValue> {
    let points: Vec<InputPoint> = serde_json::from_str(raw_points_json)
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    let config: StrokeConfig = serde_json::from_str(config_json)
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    
    let smoothed = smooth_points(&points, config.streamline_factor, config.catmullrom_alpha);
    let pressures = simulate_pressure(&points, &config);
    let outline = generate_outline(&smoothed, &pressures, &config);
    
    Ok(serde_wasm_bindgen::to_value(&outline)?)
}

// Also: record raw points during calibration (not just outline)
#[wasm_bindgen]
pub fn get_last_stroke_raw_points(&self) -> JsValue {
    // Returns the InputPoints for the most recently committed stroke
    serde_wasm_bindgen::to_value(&self.last_committed_raw_points).unwrap()
}
```

---

### 15.2 — Python: Bayesian Optimization

```python
# calibration.py
from skopt import Optimizer
from skopt.space import Real
import numpy as np

PARAM_SPACE = [
    Real(500.0, 5000.0, name="max_velocity"),
    Real(0.05, 0.5, name="min_pressure"),
    Real(0.05, 0.5, name="pressure_lerp"),
    Real(0.1, 0.9, name="streamline_factor"),
    Real(0.0, 1.0, name="catmullrom_alpha"),
    Real(-0.5, 1.0, name="thinning"),
    Real(0.1, 0.9, name="smoothing"),
]

class CalibrationSession:
    def __init__(self, pointer_type: str):
        self.pointer_type = pointer_type
        self.optimizer = Optimizer(PARAM_SPACE, base_estimator="GP", 
                                    acq_func="EI", random_state=42)
        self.history: list[tuple[list[float], int]] = []  # (params, preference: 0 or 1)
        self.current_pair: tuple[list[float], list[float]] | None = None
    
    def get_next_pair(self) -> tuple[dict, dict]:
        """Get next pair of configs for A/B comparison."""
        params_a = self.optimizer.ask()
        params_b = self.optimizer.ask()
        self.current_pair = (params_a, params_b)
        return (
            self._params_to_config(params_a),
            self._params_to_config(params_b)
        )
    
    def record_preference(self, preferred: int) -> None:
        """preferred: 0 = A was better, 1 = B was better."""
        assert self.current_pair is not None
        params_a, params_b = self.current_pair
        
        # Convert preference to a score the optimizer can learn from
        # Lower score = better (minimization)
        self.optimizer.tell(params_a, 1 - preferred)
        self.optimizer.tell(params_b, preferred)
        
        self.history.append((self.current_pair, preferred))
        self.current_pair = None
    
    def get_optimal_config(self) -> dict:
        """Returns the current best estimate of optimal config."""
        result = self.optimizer.get_result()
        return self._params_to_config(result.x)
    
    def _params_to_config(self, params: list[float]) -> dict:
        return {name: val for name, val in 
                zip([s.name for s in PARAM_SPACE], params)}
```

IPC commands:
```python
@app.command()
async def start_calibration_cmd(payload): 
    # Creates CalibrationSession, stores in service
    ...

@app.command()
async def get_calibration_pair_cmd(payload):
    # Returns two configs for A/B comparison
    ...

@app.command()
async def record_calibration_preference_cmd(payload):
    # Records which config the user preferred
    ...

@app.command()
async def finish_calibration_cmd(payload):
    # Gets optimal config, saves to device_profiles.json
    ...
```

---

### 15.3 — Svelte: Calibration UI

`Calibration.svelte` — shown on first launch or when triggered manually:

```svelte
<div class="calibration-modal">
    <h2>Calibrate for your device</h2>
    <p>Draw the same stroke below, then pick which feels better.</p>
    
    <!-- Reference stroke recording -->
    {#if phase === "record"}
        <div class="record-phase">
            <p>Step 1: Draw 3 reference strokes in this box.</p>
            <canvas bind:this={recordCanvas} ... />
            <button onclick={finishRecording} disabled={recordedStrokes < 3}>
                Continue ({recordedStrokes}/3 strokes)
            </button>
        </div>
    {/if}
    
    <!-- A/B comparison -->
    {#if phase === "compare"}
        <div class="compare-phase">
            <p>Which feels better? ({round}/{TOTAL_ROUNDS})</p>
            <div class="ab-container">
                <div class="option option-a">
                    <canvas bind:this={canvasA} ... />
                    <button onclick={() => recordPreference(0)}>A</button>
                </div>
                <div class="option option-b">
                    <canvas bind:this={canvasB} ... />
                    <button onclick={() => recordPreference(1)}>B</button>
                </div>
            </div>
        </div>
    {/if}
    
    {#if phase === "done"}
        <div class="done-phase">
            <p>✓ Calibration complete. Your canvas is tuned for this device.</p>
            <button onclick={close}>Start drawing</button>
        </div>
    {/if}
</div>
```

**A/B rendering flow:**
```typescript
async function showNextPair() {
    const { config_a, config_b } = await canvasInvoke("get_calibration_pair_cmd", {
        session_id: sessionId
    });
    
    // Replay the reference stroke through both configs
    const outlineA = engine.replay_stroke(
        JSON.stringify(referenceRawPoints), 
        JSON.stringify(config_a)
    );
    const outlineB = engine.replay_stroke(
        JSON.stringify(referenceRawPoints), 
        JSON.stringify(config_b)
    );
    
    // Render both outlines on their respective canvases
    renderOutline(ctxA, outlineA, referenceColor, referenceWidth);
    renderOutline(ctxB, outlineB, referenceColor, referenceWidth);
}
```

---

### Phase 15 Checklist for Antigravity

- [ ] `replay_stroke(raw_points_json, config_json) -> outline` WASM method
- [ ] `get_last_stroke_raw_points` WASM method
- [ ] Engine stores raw points for last committed stroke
- [ ] `scikit-optimize` added to Python dependencies
- [ ] `CalibrationSession` class with `Optimizer`
- [ ] All calibration IPC commands
- [ ] `Calibration.svelte` with record / compare / done phases
- [ ] First-launch calibration trigger (check for missing device profile)
- [ ] `TOTAL_ROUNDS = 20` constant
- [ ] Device change detection triggers calibration offer
- [ ] Calibration result saved to `device_profiles.json`
- [ ] Settings panel with "Recalibrate" button

---

## Phase 16 — Quality of Life Polish

**Goal:** The details that make the app feel professional.

---

### 16.1 — Minimap

```svelte
<div class="minimap" 
     style="position: absolute; bottom: 16px; right: 16px; opacity: {minimapOpacity};"
     onmouseenter={() => minimapOpacity = 1}
     onmouseleave={() => minimapOpacity = 0.5}>
    
    <canvas bind:this={minimapCanvas} width={160} height={120} />
    
    <!-- Viewport indicator box -->
    <div class="viewport-box" style={viewportBoxStyle} onclick={onMinimapClick} />
</div>
```

```typescript
function updateMinimap() {
    // Scale the full canvas content to minimap size
    // Draw viewport indicator box
    
    const scaleX = MINIMAP_W / totalContentBounds.w;
    const scaleY = MINIMAP_H / totalContentBounds.h;
    const scale = Math.min(scaleX, scaleY);
    
    minimapCtx.clearRect(0, 0, MINIMAP_W, MINIMAP_H);
    minimapCtx.drawImage(baseCanvas, 
        0, 0, baseCanvas.width, baseCanvas.height,
        0, 0, baseCanvas.width * scale, baseCanvas.height * scale
    );
    
    // Viewport box position and size in minimap space
    const vpX = (viewport.offsetX - totalContentBounds.x) * scale;
    const vpY = (viewport.offsetY - totalContentBounds.y) * scale;
    const vpW = (canvasEl.width / viewport.scale) * scale;
    const vpH = (canvasEl.height / viewport.scale) * scale;
    
    minimapCtx.strokeStyle = "#4A90E2";
    minimapCtx.lineWidth = 1.5;
    minimapCtx.strokeRect(vpX, vpY, vpW, vpH);
}
```

Click on the minimap to teleport the viewport to that position.

---

### 16.2 — Zoom Level HUD

```svelte
{#if showZoomHud}
    <div class="zoom-hud" 
         style="position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);"
         transition:fade={{ duration: 200 }}>
        {Math.round(viewport.scale * 100)}%
    </div>
{/if}
```

```typescript
let showZoomHud = false;
let hudTimer: number;

function onZoomChange() {
    showZoomHud = true;
    clearTimeout(hudTimer);
    hudTimer = setTimeout(() => { showZoomHud = false; }, 2000);
}
```

---

### 16.3 — Recent Colors

```typescript
const MAX_RECENT_COLORS = 8;
let recentColors: string[] = loadRecentColors();

function onColorSelected(color: string) {
    activePenColor = color;
    
    // Add to recent colors
    recentColors = [color, ...recentColors.filter(c => c !== color)]
        .slice(0, MAX_RECENT_COLORS);
    
    saveRecentColors(recentColors);
}

function saveRecentColors(colors: string[]) {
    localStorage.setItem("sushi_recent_colors", JSON.stringify(colors));
}

// Wait — no localStorage in artifacts. Use pyInvoke to persist via Python:
async function saveRecentColors(colors: string[]) {
    await canvasInvoke("save_user_preference_cmd", { 
        key: "recent_colors", 
        value: colors 
    });
}
```

Render as a row of 8 small color swatches in the toolbar below the main color picker.

---

### 16.4 — Eyedropper / Color Sampler

```typescript
async function activateEyedropper() {
    activeToolTemp = "eyedropper";
    canvas.style.cursor = "crosshair";
    
    const onPick = (e: PointerEvent) => {
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        // Sample from the base canvas (committed strokes)
        const pixel = baseCtx.getImageData(x * devicePixelRatio, 
                                             y * devicePixelRatio, 1, 1).data;
        const color = rgbToHex(pixel[0], pixel[1], pixel[2]);
        
        onColorSelected(color);
        deactivateEyedropper();
    };
    
    canvas.addEventListener("pointerdown", onPick, { once: true });
}
```

---

### 16.5 — Stroke Smoothing Live Slider

The toolbar has a smoothing slider that adjusts `streamline_factor` live:

```svelte
<label class="smoothing-control">
    <span>Smoothing</span>
    <input 
        type="range" 
        min="0" max="1" step="0.05"
        bind:value={toolConfig.streamline_factor}
        oninput={onSmoothingChange}
    />
</label>
```

`onSmoothingChange` updates the active `StrokeConfig`. Changes take effect immediately on the next stroke drawn — no WASM rebuild required because `streamline_factor` is passed per-stroke.

---

### 16.6 — Canvas Background Toggle

Dark / Light / Transparent toggle. The background canvas element's CSS background color changes:

```typescript
type CanvasTheme = "light" | "dark" | "transparent";

function setCanvasTheme(theme: CanvasTheme) {
    const colors = {
        light: { bg: "#ffffff", pattern: "#d0d0d0" },
        dark: { bg: "#1a1a2e", pattern: "#333355" },
        transparent: { bg: "transparent", pattern: "#cccccc" }
    };
    
    canvasContainerEl.style.backgroundColor = colors[theme].bg;
    bgConfig = { ...bgConfig, color: colors[theme].pattern };
    renderBackground(bgConfig, viewport);
}
```

---

### 16.7 — Keyboard Shortcut Reference Sheet

Accessible via `Ctrl+?` or from the Help menu. Rendered as a modal overlay:

```typescript
const SHORTCUTS: Record<string, string> = {
    "Ctrl+Z": "Undo",
    "Ctrl+Shift+Z": "Redo",
    "Ctrl+A": "Select All",
    "Delete / Backspace": "Delete Selection",
    "Ctrl+D": "Duplicate Selection",
    "Escape": "Deselect / Cancel",
    "Arrow Keys": "Nudge (1px)",
    "Shift+Arrow": "Nudge (10px)",
    "Space (hold)": "Pan tool",
    "Ctrl+0": "Reset zoom",
    "Ctrl+= / -": "Zoom in / out",
    "Ctrl+?": "This shortcut sheet",
    "3 fingers": "Undo (stylus)",
    "4 fingers": "Redo (stylus)",
};
```

---

### 16.8 — Grid Snapping (Optional)

When the background pattern is a grid, the user can enable "snap to grid" which snaps stroke start/end points to the nearest grid intersection:

```typescript
function snapToGridIfEnabled(x: number, y: number): [number, number] {
    if (!gridSnappingEnabled || bgConfig.type !== "grid") return [x, y];
    
    const spacing = bgConfig.spacing;
    return [
        Math.round(x / spacing) * spacing,
        Math.round(y / spacing) * spacing
    ];
}
```

Apply only to the first and last point of a stroke (start and end), not to intermediate points (would destroy natural drawing feel).

---

### Phase 16 Checklist for Antigravity

- [ ] Minimap component with viewport indicator
- [ ] Minimap click teleports viewport
- [ ] Minimap fades to 50% when not hovered
- [ ] Minimap updates on every base layer rerender
- [ ] Zoom HUD with 2s fade timer
- [ ] Recent colors row (8 swatches) in toolbar
- [ ] Recent colors persisted via Python preferences
- [ ] Eyedropper tool samples from base canvas pixel
- [ ] Smoothing slider in toolbar (live effect on next stroke)
- [ ] Canvas theme toggle (light / dark / transparent)
- [ ] `Ctrl+?` shortcut sheet modal
- [ ] Grid snapping toggle (first/last point only)

---

## Appendix A — Rust Engine Architecture Reference

### File Structure

```
canvas-engine/src/
├── lib.rs              — wasm_bindgen exports, CanvasEngine public API
├── engine.rs           — Engine struct, core state, method dispatch
├── stroke.rs           — Stroke struct, InputPoint, StrokeConfig, ToolType
├── text_object.rs      — TextObject struct
├── image_object.rs     — ImageObject struct
├── smoother.rs         — Input smoothing (Catmull-Rom, streamline filter)
├── freehand.rs         — Outline generation (pressure → polygon)
├── viewport.rs         — Pan/zoom transform, coordinate conversion
├── history.rs          — HistoryEntry enum, undo/redo stack
├── eraser.rs           — Hit testing for erase, AABB pre-filter
├── selection.rs        — Selection state, marquee, transform
├── geometry.rs         — BoundingBox, point-in-polygon, snap-to-angle
├── shapes.rs           — Shape recognition, shape-to-outline generation
├── export.rs           — SVG export
├── calibration.rs      — replay_stroke API for ML calibration
└── config.rs           — StrokeConfig, ToolConfigs, EasingType
```

### Performance Rules

- Never allocate inside the per-point hot path (`add_point_internal`)
- Pre-allocate `Vec` capacities where known: `Vec::with_capacity(expected_points)`
- Cache bounding boxes — invalidate on mutation only
- WASM boundary crossings are cheap for scalars, expensive for large byte arrays
- Return flat `Vec<f32>` for outlines rather than `Vec<[f32; 2]>` (better JS interop)
- Use `wasm_bindgen::JsValue` for complex return types, serialize with `serde_wasm_bindgen`

### Coordinate Space Convention

- All Rust engine state is in **canvas space** (arbitrary units, not pixels)
- All JS screen coordinates must be converted to canvas space before calling Rust methods
- Conversion: `canvas_x = (screen_x - viewport.offset_x) / viewport.scale`
- Viewport starts at offset (0,0) scale 1.0
- Positive Y is downward (matches canvas 2D convention)

---

## Appendix B — IPC Command Reference

### Naming Convention

All IPC commands follow `{verb}_{noun}_cmd` pattern.

### Canvas Commands

| Command | Payload | Response |
|---------|---------|----------|
| `create_canvas_file_cmd` | `{title, mode}` | `{file_id, path}` |
| `open_canvas_file_cmd` | `{path}` | `{file_id, data}` |
| `save_canvas_file_cmd` | `{file_id, canvas_data}` | `{}` |
| `delete_canvas_file_cmd` | `{file_id}` | `{}` |
| `save_canvas_block_cmd` | `{note_id, block_id, canvas_ref, canvas_data, thumbnail_data_url}` | `{thumbnail_ref, thumbnail_version}` |
| `load_canvas_block_cmd` | `{note_id, block_id, canvas_ref}` | `{canvas_data}` |
| `get_stroke_config_cmd` | `{pointer_type}` | `{config, is_default}` |
| `save_stroke_config_cmd` | `{pointer_type, config}` | `{}` |

### Book Commands

| Command | Payload | Response |
|---------|---------|----------|
| `create_book_cmd` | `{title, page_size_preset}` | `{book_id, path, first_page_id}` |
| `open_book_cmd` | `{path}` | `{book_id, metadata, page_size, pages[]}` |
| `get_page_cmd` | `{book_id, page_id}` | `{page_data}` |
| `update_page_cmd` | `{book_id, page_id, page_data}` | `{}` |
| `add_page_cmd` | `{book_id, after_page_id, name}` | `{page}` |
| `delete_page_cmd` | `{book_id, page_id}` | `{}` |
| `reorder_page_cmd` | `{book_id, page_id, new_order}` | `{}` |

### PDF Commands

| Command | Payload | Response |
|---------|---------|----------|
| `open_pdf_cmd` | `{path}` | `{pdf_id, page_count, title}` |
| `render_pdf_page_cmd` | `{pdf_id, page_num, scale}` | `{image_data, page_width_pts, page_height_pts, chars[]}` |
| `save_pdf_annotation_cmd` | `{pdf_id, page_num, annotation_data}` | `{}` |
| `load_pdf_annotation_cmd` | `{pdf_id, page_num}` | `{annotation_data}` |

### Calibration Commands

| Command | Payload | Response |
|---------|---------|----------|
| `start_calibration_cmd` | `{pointer_type}` | `{session_id}` |
| `get_calibration_pair_cmd` | `{session_id}` | `{config_a, config_b}` |
| `record_calibration_preference_cmd` | `{session_id, preferred}` | `{}` |
| `finish_calibration_cmd` | `{session_id}` | `{optimal_config}` |

### Utility Commands

| Command | Payload | Response |
|---------|---------|----------|
| `log_error_cmd` | `{source, message, stack?, timestamp}` | `{}` |
| `save_user_preference_cmd` | `{key, value}` | `{}` |
| `get_user_preference_cmd` | `{key}` | `{value}` |
| `import_canvas_image_cmd` | `{canvas_id, image_data, filename}` | `{resource_id, width, height, path}` |
| `get_resource_bytes_cmd` | `{path}` | `{data: number[]}` |
| `create_canvas_snippet_cmd` | `{source_type, source_id, ...}` | `{snippet_block_id}` |
| `navigate_to_canvas_region_cmd` | `{source_type, source_id, region}` | `{}` |

---

## Appendix C — File Format Schemas

### .jcanvas (Infinite Canvas)

```json
{
  "metadata": {
    "file_id": "uuid-v4",
    "title": "string",
    "created_at": "ISO-8601",
    "last_modified": "ISO-8601",
    "version": "1.0",
    "mode": "canvas"
  },
  "background": {
    "type": "none|dots|grid|lines|ruled|dotted|cornell|music_staff|isometric|custom",
    "color": "#hex",
    "spacing": 20,
    "tile_ref": null
  },
  "viewport": {
    "offset_x": 0.0,
    "offset_y": 0.0,
    "scale": 1.0
  },
  "strokes": [
    {
      "id": 12345,
      "points": [{"x": 0.0, "y": 0.0, "pressure": 0.5, "timestamp": 1234.5}],
      "outline": [[0.0, 0.0], [1.0, 0.0]],
      "color": [0.0, 0.0, 0.0, 1.0],
      "width": 4.0,
      "tool": "pen|highlighter|marker",
      "opacity": 1.0,
      "metadata": null
    }
  ],
  "text_objects": [
    {
      "id": 99,
      "x": 100.0, "y": 200.0, "w": 200.0,
      "content": "string",
      "font_family": "Inter",
      "font_size": 16.0,
      "color": [0.0, 0.0, 0.0, 1.0],
      "bold": false, "italic": false,
      "align": "Left",
      "metadata": null
    }
  ],
  "image_objects": [
    {
      "id": 77,
      "resource_id": "uuid",
      "x": 0.0, "y": 0.0, "w": 400.0, "h": 300.0,
      "original_w": 800.0, "original_h": 600.0,
      "opacity": 1.0,
      "metadata": null
    }
  ],
  "resources": {
    "uuid": "relative/path/to/image.png"
  }
}
```

### .jbook (Notebook)

```json
{
  "metadata": {
    "file_id": "uuid-v4",
    "title": "string",
    "created_at": "ISO-8601",
    "last_modified": "ISO-8601",
    "version": "1.0",
    "mode": "notebook"
  },
  "page_size": {
    "preset": "A4|A5|US_LETTER|US_HALF|SQUARE|CUSTOM",
    "width_mm": 210,
    "height_mm": 297
  },
  "pages": [
    {
      "page_id": "uuid-v4",
      "name": "Page 1",
      "order": 0,
      "background": {
        "type": "none",
        "color": "#e0e0e0",
        "spacing": 20
      },
      "strokes": [],
      "text_objects": [],
      "image_objects": []
    }
  ],
  "resources": {
    "uuid": "relative/path/to/image.png"
  }
}
```

### canvas-snippet block in .jnote

```json
{
  "block_id": "short-hex",
  "type": "canvas-snippet",
  "data": {
    "source_type": "canvas_block|infinite_canvas|pdf_annotation",
    "source_id": "uuid",
    "source_block_id": "block_id or null",
    "source_page": 0,
    "region": {"x": 100.0, "y": 80.0, "w": 400.0, "h": 200.0},
    "snapshot_ref": "snippet-uuid.png",
    "snapshot_version": 1,
    "update_mode": "auto_silent|notify|manual"
  },
  "version": "1.0",
  "tags": [],
  "backlinks": [
    {"type": "canvas_region_ref", "target_id": "source-canvas-uuid"}
  ]
}
```

---

*This document is the implementation authority for all Sushi Canvas development. Each phase should be treated as a self-contained brief. Update this document as decisions are made and phases are completed.*
