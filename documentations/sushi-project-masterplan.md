# Sushi — Complete Project Master Plan
### A Living Technical Document

> This document covers the full architecture, vision, current state, and long-term phased roadmap for the Sushi project — a local-first, block-based knowledge system with integrated drawing, PDF annotation, and AI capabilities.

---

## Table of Contents

1. [Project Vision](#1-project-vision)
2. [What Sushi Is](#2-what-sushi-is)
3. [Current State of Sushi Notes](#3-current-state-of-sushi-notes)
4. [Current State of Sushi Canvas](#4-current-state-of-sushi-canvas)
5. [The Three Canvas Modes](#5-the-three-canvas-modes)
6. [The .jnote File Format & Block System](#6-the-jnote-file-format--block-system)
7. [Resource & File Management](#7-resource--file-management)
8. [The Integration Architecture](#8-the-integration-architecture)
9. [PDF Annotation System](#9-pdf-annotation-system)
10. [The Snippet & Deep Linking System](#10-the-snippet--deep-linking-system)
11. [Planned Features Across All Modules](#11-planned-features-across-all-modules)
12. [The ML Calibration System](#12-the-ml-calibration-system)
13. [Phased Roadmap](#13-phased-roadmap)
14. [Open Problems & Unresolved Decisions](#14-open-problems--unresolved-decisions)
15. [Tech Stack Reference](#15-tech-stack-reference)

---

## 1. Project Vision

Sushi is being built as the best possible personal knowledge system for people who think visually, write technically, and work with dense source material like research papers and PDFs. The closest analogues are Obsidian, GoodNotes, and Notion — but Sushi is not trying to be any of them. It is its own thing.

**The core philosophy:**
- Everything is a block. A note is just an ordered list of typed blocks.
- All blocks are linkable, referenceable, and composable with each other.
- Drawing is not a separate app — it is a first-class block type in the note editor.
- PDF reading is not a separate app — it is a view mode with a canvas overlay.
- The file system is the database. Notes are `.jnote` files on disk. There is no proprietary cloud sync, no hidden database engine, no lock-in.
- Local-first always. The app works completely offline.

**What makes Sushi different from everything else:**
- Unlike Obsidian: Sushi has native drawing, PDF annotation, and visual canvas as core block types — not plugins.
- Unlike GoodNotes: Sushi has a structured block editor, LaTeX, code blocks, AI, and a full knowledge graph — not just notebooks.
- Unlike Notion: Sushi is local-first, privacy-preserving, and treats handwriting as equal to typed text.
- Unlike all of them: Sushi has a unified coordinate system across all content types — a drawn annotation on a PDF can link to a typed note block, and a canvas snippet can embed in a note and stay live.

The long-term vision is a tool where a student, researcher, or knowledge worker can do everything in one place: read a paper, annotate it, draw a concept map, write up their understanding in structured notes, and have the AI help them connect ideas across their entire knowledge base.

---

## 2. What Sushi Is

At its core, Sushi is three things fused together:

### 2.1 Sushi Notes (The Block Editor)
A local-first, block-based note editor. Think Obsidian's file system philosophy combined with Notion's block model. Notes are `.jnote` JSON files. Each note is an ordered array of blocks. Each block has a type, and each type is rendered by its own Svelte component in the editor.

Current block types: `text`, `todo`, `code`, `latex`, `image`.
Planned block types: `canvas`, `pdf`, `jupyter`, `canvas-snippet`.

### 2.2 Sushi Canvas (The Drawing Engine)
A professional-grade drawing engine built in Rust, compiled to WASM, with a Svelte frontend. Currently a standalone PyTauri app. Will be integrated into Sushi Notes as a block type and as a standalone view mode.

The canvas engine handles all stroke math in Rust — smoothing, pressure simulation, outline generation, viewport transforms, undo/redo, hit testing. The Svelte layer handles rendering and input only.

### 2.3 Sushi PDF (The Annotator)
A PDF reader with a canvas annotation overlay. Uses `pdfium-render` (Rust bindings to Google's PDFium) compiled to WASM for pixel-accurate text extraction and rendering. The annotation canvas is a finite, page-locked version of Sushi Canvas. Strokes are stored separately from the PDF in a sidecar file.

---

## 3. Current State of Sushi Notes

### 3.1 What Is Built
- Full block editor with `text`, `todo`, `code`, `latex` block types
- Hierarchical file tree with drag-and-drop
- Full-text keyword search (SQLite FTS5)
- Semantic search (FAISS + Gemini embeddings)
- RAG-powered AI assistant sidebar
- Real-time filesystem watching with hot-swap on external edits
- Block and note linking via `[[ display-text | link-type | link-id ]]` syntax
- Backlinks scaffold on each block (populated later for graph view)
- Auto-save with debounce and echo suppression
- In-memory SQLite index rebuilt on launch for fast lookups

### 3.2 Technology Stack
| Layer | Technology |
|---|---|
| Desktop Shell | Rust / Tauri v2 |
| Backend Logic | Python 3.x via PyO3 |
| IPC Bridge | `tauri-plugin-pytauri-api` |
| Frontend | SvelteKit (Svelte 5) + TypeScript |
| Styling | TailwindCSS v4 |
| Build | Vite + Cargo |
| Python Env | `uv` |

### 3.3 Backend Architecture
The entire backend runs as a single `VaultService` instance — the "brain" of the app. It owns:
- `FileIndex` — an in-memory SQLite database of all notes and directories, rebuilt on every launch
- `VaultWatcher` — a watchdog filesystem observer that detects external edits
- `ActiveFileTree` — emits `tree-changed` events to the frontend when files move
- `_active_notes` — a registry of `ActiveNote` instances, one per open note

Each `ActiveNote` handles: loading from disk, merging frontend edits, debounced auto-save (2.5s), echo suppression (ignores its own saves), and hot-swap on external edits.

### 3.4 The Non-Reactive Editing Pattern
`MainArea.svelte` deliberately uses plain JavaScript variables (not `$state()`) for block content during editing. This is a critical design decision — Svelte reactivity would re-render the entire block list on every keystroke, destroying `contenteditable` cursor position and causing lag. Instead:
- Block components own their `contenteditable` DOM
- Content changes are captured via `oninput` into a plain JS map
- Saves are triggered by a debounced `triggerSave()` that reads from the map
- `rerenderBlocks()` forces a destroy/recreate cycle only for structural changes

The Canvas block will follow the same philosophy — the canvas engine owns its state, not Svelte.

### 3.5 The `.jnote` File Format
```json
{
  "metadata": {
    "note_id": "uuid-v4",
    "title": "My Note",
    "created_at": "ISO-8601",
    "last_modified": "ISO-8601",
    "version": "1.0",
    "status": 0,
    "tags": [],
    "last_known_path": "/absolute/path/to/file.jnote"
  },
  "blocks": [
    {
      "block_id": "short-hex-id",
      "type": "text|todo|code|latex|image|canvas|pdf|canvas-snippet",
      "data": { "content": "..." },
      "version": "1.0",
      "tags": [],
      "backlinks": []
    }
  ],
  "custom_fields": {}
}
```

### 3.6 Known Limitations (Current)
- No automated tests — manual smoke testing only
- In-memory `FileIndex` rebuilt on every launch (no persistence)
- Single vault — no multi-vault support
- Hardcoded dev vault path
- `MainArea.svelte` is ~850 lines and needs further extraction
- GraphRAG intentionally removed, pending better implementation
- No offline-first sync

---

## 4. Current State of Sushi Canvas

### 4.1 What Is Built
Sushi Canvas is currently a **standalone PyTauri app** — same tech stack as Sushi Notes but a completely separate project. It has:

- Rust WASM drawing engine (`canvas-engine` crate) with:
  - Catmull-Rom spline smoothing
  - Velocity-based pressure simulation
  - `perfect_freehand`-style polygon outline generation with pressure-sensitive width
  - Undo/redo stack (command pattern, 100-entry limit)
  - Pan/zoom viewport (infinite canvas)
  - Eraser with AABB pre-filter + polygon boundary hit testing
  - SVG export
  - Serialize/deserialize for save/load
  - Dot fallback for single-tap clicks
- Svelte frontend with:
  - Two-layer canvas (base layer + active layer for performance)
  - Pointer event handling with coalesced events (240hz stylus support)
  - Two-finger pinch-to-zoom and pan gesture system with pointer state machine
  - Cursor/pan tool
  - Device pixel ratio handling for retina displays
  - Toolbar with pen, highlighter, marker, eraser, cursor tools
  - Color swatches + size slider
  - Undo/Redo/Save/Load/Export SVG buttons
  - Keyboard shortcuts

### 4.2 Known Issues (Current Canvas State)
- Select tool not yet implemented
- No text tool
- No image import
- No layers
- No straight line / shape recognition
- No background pattern/grid system
- No infinite canvas file format yet
- Single canvas only — no multi-page

### 4.3 Canvas Engine Architecture Principle
The architecture follows a strict separation:

**Rust WASM = The Brain** — owns all state and math:
- Stroke data model (`Vec<Stroke>`)
- All smoothing and outline computation
- Viewport transform state
- Undo/redo history
- Hit testing

**Svelte/JS = The Hands** — owns all I/O and rendering:
- Capturing raw `PointerEvent` coordinates
- Making all `Canvas2DRenderingContext` draw calls
- Rendering the toolbar UI
- Keyboard shortcuts

This split exists because `web-sys` Canvas2D calls from Rust cross the WASM boundary on every call, creating overhead. Rust returns flat float arrays, JS renders in a tight loop. This is the same pattern used by tldraw and Excalidraw internally.

---

## 5. The Three Canvas Modes

### 5.1 Canvas Block (Embedded in a Note)

**What it is:** A fixed-size drawing page embedded inside a `.jnote` as a block. Analogous to a single GoodNotes page embedded in a note.

**Behavior:**
- Default size: A4 (210mm × 297mm)
- Preset sizes: A4, A5, US Letter, US Half Letter, square, custom
- When not focused: renders as a static thumbnail image of the canvas content
- When focused (clicked): expands in place within the note, the rest of the note remains visible above and below
- When blurred (click elsewhere): collapses back to thumbnail
- Canvas has its own internal viewport — the user can pan and zoom within the fixed page boundary
- To add more canvas space: add another canvas block below — each is its own independent page

**Storage:**
- The `.jnote` block `data` field contains only a reference:
```json
{
  "type": "canvas",
  "data": {
    "canvas_ref": "canvas-uuid.jcanvas",
    "size": { "preset": "A4", "width_mm": 210, "height_mm": 297 },
    "thumbnail_ref": "canvas-uuid-thumb.png"
  }
}
```
- Actual stroke data lives in `.resources/canvas-uuid.jcanvas`
- Thumbnail lives in `.resources/canvas-uuid-thumb.png`
- Thumbnail is regenerated on every save of the canvas

**Interactions with the block system:**
- Canvas block participates in block drag reorder like all other blocks
- Block toolbar above the canvas block shows: resize page, add page below, delete block
- Keyboard shortcuts (Ctrl+Z etc.) are scoped to the canvas when it is focused, and to the note editor when canvas is not focused

---

### 5.2 Infinite Canvas (Standalone File)

**What it is:** A standalone canvas document in the vault. Not embedded in a note. Opened from the sidebar like a note. Full main area takeover, infinite space.

**Behavior:**
- Opened from the file tree sidebar — appears in the main area tab
- Infinite pan and zoom (no page boundaries)
- Optional tiling background pattern
- Background patterns: presets (dots, grid, lines, isometric, music staff, cornell lines) and later user-uploaded SVG/image tile
- User can define a rectangular tile and Sushi will repeat it infinitely as the background
- The background pattern scales and moves with the viewport

**File format:**
- Stored as `.jcanvas` in the vault
- Filename convention follows the same `{slug}-{short_id}.jcanvas` pattern as `.jnote`
- The format is JSON — strokes array, viewport state, background config, metadata
- Registered in `FileIndex` alongside notes so it appears in the sidebar and search

**The `.jcanvas` format (planned):**
```json
{
  "metadata": {
    "canvas_id": "uuid-v4",
    "title": "My Canvas",
    "created_at": "ISO-8601",
    "last_modified": "ISO-8601",
    "version": "1.0"
  },
  "mode": "infinite",
  "background": {
    "type": "dots|grid|lines|none|custom",
    "tile_ref": null,
    "color": "#e0e0e0",
    "spacing": 20
  },
  "viewport": {
    "offset_x": 0,
    "offset_y": 0,
    "scale": 1.0
  },
  "strokes": [...],
  "text_objects": [...],
  "image_objects": [...]
}
```

---

### 5.3 PDF Annotation Canvas (Overlay on PDF Page)

**What it is:** A finite canvas overlay locked to the dimensions of a PDF page. When viewing a PDF, the annotation canvas sits transparently on top of each page. The user can draw, highlight, and annotate directly on the PDF.

**Behavior:**
- Each PDF page gets its own independent annotation canvas
- The canvas coordinate system matches the PDF page dimensions (PDF points at 72dpi base)
- When the user zooms the PDF, the canvas transform follows — both scale together, corners always match
- The annotation canvas has the full Sushi Canvas toolset: pen, highlighter, marker, eraser, text tool
- Text selection mode and drawing mode are toggled via the tool panel — pointer events are routed to the appropriate layer
- Highlights are drawn as semi-transparent strokes using the highlighter tool on the canvas layer (not as PDF text highlights via PDF.js)

**Storage:**
- PDF files live in the vault as regular files
- Each PDF gets a UUID assigned on first import into Sushi
- Annotation strokes are stored in a sidecar file in the nearest `.resources` folder
- Sidecar file structure: one `.jcanvas` annotation file per PDF page
- The `.resources` folder maps PDF UUID → array of per-page annotation files

**The file matching problem:**
- If the PDF is moved or renamed within Sushi: the UUID-based system handles this transparently
- If the PDF is modified externally (different version, re-exported): the UUID changes, annotations become orphaned
- Planned handling: the user is notified and can manually re-link the annotation to the new PDF version
- This is acknowledged as a hard problem with no perfect solution

**Why pdfium-render instead of PDF.js:**
PDF.js uses two independent pipelines — a canvas renderer and a text layer — that use different font measurement systems. The text layer applies a CSS `scaleX` approximation to match rendered glyph widths, which fails with embedded fonts, custom character spacing, and non-standard scales. This is a structural limitation, not a fixable bug.

`pdfium-render` is Rust bindings to Google's PDFium engine (the same engine Chrome uses). It uses a single pipeline for both rendering and text extraction. The `FPDFText_GetCharBox` API returns exact per-character bounding boxes from the actual glyph data. The visual render and the text coordinate map are guaranteed to be consistent because they come from the same engine.

In Tauri, the PDF bytes are read by the Python backend and passed across the IPC bridge to the WASM layer — filesystem APIs are not available in WASM context.

---

## 6. The .jnote File Format & Block System

### 6.1 Block Registration
Each block type is a Svelte component in `src/lib/components/editor/`. Adding a new block type means:
1. Creating the Svelte component (`CanvasBlock.svelte`, etc.)
2. Registering it in `MainArea.svelte`'s block renderer switch
3. Adding the type to `note_schema.py` in the Python backend
4. Adding any required IPC commands to `commands.py` if the block needs backend operations

### 6.2 The Canvas Block Schema
```json
{
  "block_id": "hex-id",
  "type": "canvas",
  "data": {
    "canvas_ref": "uuid.jcanvas",
    "size": {
      "preset": "A4 | A5 | US_LETTER | US_HALF | SQUARE | CUSTOM",
      "width_mm": 210,
      "height_mm": 297
    },
    "thumbnail_ref": "uuid-thumb.png",
    "thumbnail_version": 3
  },
  "version": "1.0",
  "tags": [],
  "backlinks": []
}
```

### 6.3 The Canvas Snippet Block Schema
A canvas snippet is a static embed of a rectangular region from a canvas source. It is a separate block type, not a subtype of canvas.

```json
{
  "block_id": "hex-id",
  "type": "canvas-snippet",
  "data": {
    "source_type": "canvas_block | infinite_canvas | pdf_annotation",
    "source_id": "uuid of source canvas or note",
    "source_block_id": "block_id if source is a canvas block",
    "source_page": 2,
    "region": { "x": 120, "y": 80, "w": 400, "h": 200 },
    "snapshot_ref": "snippet-uuid.png",
    "snapshot_version": 1,
    "update_mode": "auto_silent | notify | manual"
  },
  "version": "1.0",
  "tags": [],
  "backlinks": [
    { "type": "canvas_region_ref", "target_id": "source canvas uuid" }
  ]
}
```

### 6.4 The Link Syntax
Within block content (markdown, rich text), links follow:
```
[[ display-text | link-type | link-id ]]
```

For canvas snippets embedded in text, the same syntax will be used but rendered as an inline image preview. Link types planned for canvas:
- `canvas_block` — links to a canvas block in a note
- `canvas_file` — links to a standalone `.jcanvas` file
- `canvas_region` — links to a specific region of a canvas
- `pdf_page` — links to a specific page of a PDF
- `pdf_region` — links to a specific rectangular region of a PDF page

---

## 7. Resource & File Management

### 7.1 The `.resources` Folder
Every directory in the vault has a hidden `.resources` folder. This folder stores all binary and large assets associated with notes in that directory:
- Canvas files (`.jcanvas`)
- Thumbnails (`.png`)
- Images imported into notes
- PDF annotation sidecars

The `.resources` folder is keyed by note/canvas UUID — not by filename. This means if a note is renamed, its resources are still findable.

### 7.2 The Persistent Resource Database
The `VaultService` maintains a persistent mapping of:
- `resource_id` → `resource_path` on disk
- `note_id` → `[resource_ids]`

When the filesystem watcher detects a note move:
1. The watcher fires a `move` event
2. `VaultService.on_file_event` catches it
3. The resource mapping is updated to point to the new `.resources` location
4. Resources are physically moved if needed
5. `FileIndex` is updated

When a note is deleted:
1. All resources associated with that note are deleted
2. The resource mapping entries are removed
3. Any canvas snippets in other notes that referenced this note are notified (broken link handling)

### 7.3 The Bundling/Export Problem
This is an **acknowledged unresolved problem**. The current thinking:

When a user wants to export a note (share it, move it to another vault, back it up):
1. A packager collects the `.jnote` file and all entries from the resource mapping
2. It creates a `.sushi` archive (essentially a ZIP with a manifest)
3. The manifest lists all resources and their original relative paths
4. On import into another vault, the manifest is read and resources are extracted to the new vault's `.resources` folder with remapped IDs

This is not yet implemented. The exact format of the `.sushi` archive is not decided. The problem of handling broken resource references during partial imports is not solved.

### 7.4 PDF UUID and Sidecar Matching
On first import of a PDF into Sushi:
1. Python backend generates a UUID for that PDF instance
2. A `.resources/pdf-annotations/{pdf-uuid}/` directory is created
3. Annotation sidecars (`page-1.jcanvas`, `page-2.jcanvas`, etc.) are created there as needed

If the same PDF is imported twice: it gets two different UUIDs and two separate annotation sets. This is intentional — two copies of a PDF could be annotated independently.

If the PDF is externally modified: the UUID stays the same (it's Sushi's identifier, not derived from the PDF content). The annotations remain linked. However if the page count changes or pages are reordered, annotations may be misaligned. This edge case is not yet handled and is acknowledged as a hard problem.

Checksum-based matching was considered but rejected: importing the same PDF twice would create a match and merge annotations that the user may want separate.

---

## 8. The Integration Architecture

### 8.1 The Merge Plan
Sushi Canvas will not be merged into Sushi Notes via iframe, a second Tauri window, or a monorepo package system. The integration is direct:

1. The `canvas-engine` Rust WASM crate moves from `sushi-canvas/canvas-engine/` into the Sushi Notes workspace
2. The Canvas Svelte components (`Canvas.svelte`, `Toolbar.svelte`, `renderer.ts`, `engine.ts`, `input.ts`) are adapted and placed in `sushi/src/lib/components/editor/`
3. `vite.config.js` in Sushi Notes gets the `canvas-engine` alias
4. `Cargo.toml` workspace in Sushi Notes adds `canvas-engine` as a member
5. `CanvasBlock.svelte` is registered as a block type in `MainArea.svelte`

Sushi Canvas the standalone app remains alive as a development sandbox during this process. It is the testbed — changes to the Rust engine are developed and tested there, then the WASM crate is updated in Sushi Notes.

### 8.2 The Phased Integration Approach
Integration does not happen all at once. The phases are:

**Phase 1:** Canvas lives as a second tab in Sushi Notes nav rail — completely independent, no wiring. The user can switch between Notes view and Canvas view. This validates the build integration.

**Phase 2:** Canvas Block — `CanvasBlock.svelte` is a real block type. Canvas files are created, saved, and loaded through `VaultService`. Thumbnails are generated. The block collapses and expands.

**Phase 3:** Infinite Canvas as a vault file type — `.jcanvas` files appear in the sidebar, can be created, opened, and managed like notes.

**Phase 4:** PDF viewer and annotation canvas.

**Phase 5:** Canvas snippets and deep linking.

### 8.3 The CanvasBlock Component Contract
`CanvasBlock.svelte` must follow the same contract as all other block components:
- Receives `block` (the block data object) and `noteId` as props
- Emits a `change` event with new block data when content changes (triggering the note's debounced save)
- Does NOT use Svelte `$state()` for canvas content — canvas engine owns that state
- Manages focus/blur state internally — expanded when focused, thumbnail when blurred
- On blur: triggers thumbnail regeneration and saves canvas file via `pyInvoke`

### 8.4 The Canvas Save Flow
```
User draws stroke
  → canvas engine accumulates state in Rust
  → on pointerup → stroke committed to Rust engine

User blurs canvas block (clicks elsewhere)
  → CanvasBlock.svelte detects blur
  → calls engine.serialize() → JSON string
  → pyInvoke("save_canvas_block", { noteId, blockId, canvasData })
  → Python backend writes to .resources/uuid.jcanvas
  → CanvasBlock re-renders thumbnail from current canvas state
  → thumbnail written to .resources/uuid-thumb.png
  → block data updated with new thumbnail_version
  → triggers note save (like any other block content change)
```

---

## 9. PDF Annotation System

### 9.1 Layer Architecture
Three layers stacked via `position: absolute`, same dimensions:

```
Layer 3 — Sushi Canvas (Rust WASM)
  Drawing, ink, text annotations, highlights
  Active when: draw mode, highlight mode, annotation mode

Layer 2 — Hit Testing & Text Selection
  Per-character { char, x, y, w, h } map
  Built from FPDFText_GetCharBox output
  Active when: text selection mode

Layer 1 — pdfium-render WASM
  Renders page as bitmap to base canvas
  Outputs character bounding box data
  Always visible, never captures pointer events directly
```

`pointer-events` CSS is toggled on layers to route input to the correct layer based on the active tool. This switch happens at zero cost — no re-renders, just a CSS property change.

### 9.2 pdfium-render Integration
The PDFium WASM module handles:
- Rendering each PDF page to a bitmap at the requested zoom level
- Extracting all character positions via `FPDFText_GetCharBox`
- Returning a flat array of `{ char: string, x: f64, y: f64, w: f64, h: f64 }` structs

The Tauri Python backend reads the PDF file and passes bytes to the WASM layer via the IPC bridge. This is required because WASM cannot access the filesystem directly.

### 9.3 Coordinate System
- Base coordinate system: PDF user-space (72 points per inch)
- At 100% zoom: 1 PDF point ≈ 1 CSS pixel (at 96dpi screen)
- The canvas overlay uses the same coordinate transform as the PDF renderer
- When the user zooms: both the PDF bitmap and the canvas `ctx.setTransform()` are updated with the same scale factor
- This guarantees strokes always align with the PDF content they annotate, regardless of zoom level
- Stored stroke coordinates are in PDF user-space (not screen pixels) — zoom-independent

### 9.4 Text Selection & Highlight Flow
```
User drags across text in selection mode
  → pointer events routed to Layer 2
  → hit test against character bounding box map
  → compute selection rect as union of selected char bboxes
  → visual selection highlight shown as semi-transparent overlay

User confirms highlight (releases pointer)
  → selection rect converted to a canvas highlighter stroke
  → stroke added to the annotation canvas (Layer 3)
  → stored in page annotation sidecar
  → can be erased with eraser tool like any other stroke
```

This means PDF text highlights ARE canvas strokes — they participate in undo/redo, can be resized with the select tool, and are rendered by the same drawing engine as hand-drawn ink.

### 9.5 The "Select PDF Region → Create Note Block" Flow
This is the killer feature for research workflows:

```
User selects a rectangular region of a PDF page
  (either a text region or any arbitrary area)
  → region coordinates captured in PDF user-space
  → snapshot image of that region rendered from the PDF bitmap
  → user chooses: "Copy as snippet" or "Link to note"

"Link to note":
  → creates a canvas-snippet block in the active note
  → block data stores: pdf_id, page_number, region rect
  → snapshot image stored in .resources as thumbnail
  → backlink recorded in the snippet block pointing to the PDF
  → clicking the snippet in the note: opens the PDF at that page,
    scrolls to and highlights the source region
```

---

## 10. The Snippet & Deep Linking System

### 10.1 What a Snippet Is
A canvas snippet is a static image embed of a rectangular region of any canvas source (canvas block, infinite canvas file, or PDF page). It lives in a note as its own block type.

### 10.2 Snippet Lifecycle

**Creation:**
1. User activates the "Region Select" tool in any canvas mode
2. Drags a rectangle over the content they want to capture
3. Chooses "Create Snippet" from the context menu
4. Chooses destination note and position
5. Snapshot image is rendered and stored in `.resources`
6. A `canvas-snippet` block is inserted in the destination note

**Display:**
- The snippet block renders as an image (the snapshot) with a small source indicator
- A subtle icon or badge shows it is a live-linked snippet (not just a pasted image)
- Clicking the image opens the source canvas/PDF/note at the exact region

**Updates:**
The snippet has three update modes, user-configurable per snippet:
- `auto_silent` — snapshot is regenerated in the background whenever the source region changes. The note gets the new image silently.
- `notify` — a small badge appears on the snippet indicating it has changed. User clicks to refresh.
- `manual` — snippet never auto-updates. User must right-click → "Refresh Snippet" manually.

The system that detects changes: when any canvas file is saved, the system checks if any snippets reference regions within that canvas. For each matching snippet, it re-renders the region and either auto-updates or marks as stale, depending on the update mode.

**Broken links:**
If the source canvas file is deleted:
- The snapshot image is preserved in `.resources`
- The snippet block adds a visual "source deleted" indicator
- User is prompted: "Keep as static image" or "Delete snippet"
- If "Keep as static image": the `type` changes from `canvas-snippet` to `image`, backlinks are cleared

### 10.3 Deep Link Navigation
Every `canvas-snippet` block and every `[[link]]` referencing a canvas region stores enough information to navigate back to the source:
- `source_id` — UUID of the source canvas file or note
- `source_page` — page number (for PDF or multi-page canvas)
- `region` — `{ x, y, w, h }` in canvas coordinates

When the user clicks a snippet or follows a canvas region link:
1. The app checks if the source file is open (in an active tab or the current main view)
2. If yes: navigate to it and animate/highlight the source region
3. If no: open the source file in the main area, then navigate to the region
4. If deleted: show the broken link dialog

The navigation mode (open in current view vs open in new panel) is a **user setting** that has not been decided yet. Both options will be supported — the default will likely be "open in current view" to keep the UI simple initially, with panel/split view as a later addition.

---

## 11. Planned Features Across All Modules

### 11.1 Canvas Features (Sushi Canvas Engine)

**Select Tool** (next major feature)
- Marquee drag to select all strokes completely inside the box
- Click to select individual stroke
- Ctrl/Shift+click to add/remove from selection
- Drag to move selected strokes (60fps visual feedback in JS, single commit to Rust on release)
- 8 resize handles on bounding box
- Rotate handle above bounding box
- Delete/Backspace to erase selection
- Ctrl+D to duplicate selection
- Arrow keys to nudge (1px), Shift+Arrow to nudge (10px)
- Escape to deselect
- Undo/redo for all transform operations
- History entries: `TransformStrokes`, `DuplicateStrokes`

**Text Tool**
- Click anywhere to place a text object
- Choose font, size, color, weight
- Text objects are selectable, moveable, resizable with the select tool
- Text is stored as structured data (not rasterized) so it remains editable
- Used as the bridge to OCR in a future phase (handwritten stroke → text object)

**Image Import**
- Drag and drop image files onto the canvas
- Image becomes a selectable/resizable object
- Used for reference images while drawing, or annotating screenshots
- Stored in `.resources`, referenced by UUID in canvas data

**Straight Line / Shape Mode**
- Hold Shift while drawing: snap to straight line
- Hold for ~1 second after completing a shape: shape recognition kicks in
- Recognized shapes: line, rectangle, circle, triangle, arrow
- Recognized shape replaces the freehand stroke with a clean geometric version
- User can dismiss (keep freehand) or accept (replace with clean shape)

**Background Patterns (Infinite Canvas)**
- Presets: none, dots, small grid, large grid, lines, isometric, music staff, Cornell notes template
- Custom: upload a valid SVG or image, Sushi tiles it infinitely
- Background is visual only — strokes are drawn on top, pattern doesn't affect export unless user explicitly chooses "export with background"
- Pattern scales and pans with the viewport

**Symmetry Mode** (later)
- Mirror drawing: draw on one half, mirror appears on the other
- Radial symmetry: draw in one segment, repeated N times around center
- Both horizontal/vertical mirror and radial modes

**ML Calibration System** (see Section 12)

### 11.2 Notes Features (Sushi Notes Editor)

**Canvas Block**
- Fixed size page embedded in note
- A4 default, preset sizes, custom size picker
- Thumbnail when collapsed, full canvas when focused
- Multiple canvas blocks = multiple pages
- Future: group canvas blocks into a named "notebook group"

**Jupyter Code Block**
- Separate block type from the general `code` block
- Embedded Python execution environment
- Cell-based execution with output display
- State persists within a note session
- Integration with the Python backend running in the Tauri process

**Backlinks Tab**
- Right panel tab showing all notes that link to the current note
- Includes canvas region references, snippet embeds, and `[[link]]` mentions
- Foundation for the knowledge graph view

**Knowledge Graph View**
- Visual node-graph of note connections
- Nodes: notes, canvas files, PDFs
- Edges: `[[links]]`, backlinks, snippet references, canvas region links
- Second implementation of GraphRAG — the first was removed, a better version will be built with cleaner architecture

**Search Improvements**
- Search inside canvas text objects
- Search inside PDF annotation text
- Semantic search across all content types (currently notes only)

### 11.3 PDF Features

**PDF Viewer**
- Rendered via `pdfium-render` WASM
- Per-page rendering at current zoom level
- Smooth zoom and pan
- Page thumbnail strip sidebar
- Keyboard navigation (arrow keys, Page Up/Down)

**Text Selection & Copy**
- Drag to select text using the per-character bounding box map
- Ctrl+C to copy selected text
- Selected text can be dragged to create a quote block in a note

**Highlights as Canvas Strokes**
- Highlights are semi-transparent canvas strokes on the annotation layer
- Participate in undo/redo
- Can be erased with the canvas eraser
- Different highlight colors via color picker

**PDF Annotation Sidebar**
- List of all annotations on the current PDF (strokes, text objects, highlights)
- Click annotation in sidebar → navigates to its page and location
- Annotations can be tagged and named

### 11.4 Quality of Life Features

**Minimap**
- Small thumbnail of the full infinite canvas in a corner
- Shows current viewport position as a highlighted box
- Clickable — click on the minimap to teleport the viewport
- Fades when not in use

**Zoom Level HUD**
- Small percentage indicator in the corner
- Appears on zoom, fades after 2 seconds of inactivity

**Recent Colors**
- Row of the last 8 colors used, shown in the toolbar color section
- Persists across sessions

**Eyedropper / Color Picker**
- Click anywhere on the canvas to sample that color as the active color

**Stroke Smoothing Slider**
- Exposes the `STREAMLINE_FACTOR` Rust constant as a live UI slider
- Changes take effect immediately (no WASM rebuild — this is a parameter passed per-stroke)

**Dark / Light Canvas Background Toggle**
- Draw on white (for print/export), dark (for screens), or transparent

**Canvas Grid Snapping**
- Optional: snap stroke start/end points to the background grid

---

## 12. The ML Calibration System

### 12.1 The Problem It Solves
The Sushi Canvas drawing engine has several tunable parameters that control stroke feel:
- `MAX_VELOCITY` — how speed maps to pressure
- `MIN_PRESSURE` — minimum stroke width
- `PRESSURE_LERP` — how fast pressure reacts
- `STREAMLINE_FACTOR` — how much input is smoothed
- `thinning` — how much pressure affects width
- `smoothing` — Catmull-Rom smoothing intensity
- `catmullrom_alpha` — centripetal vs uniform Catmull-Rom

The optimal values for these parameters are different for every input device and every user's drawing style. A mouse user needs different smoothing than a stylus user. A fast sketcher needs different pressure curves than someone who draws slowly and deliberately.

### 12.2 The Approach: Preference-Based Bayesian Optimization
The user is shown pairs of strokes rendered with different parameter vectors and asked "which feels better?" After ~15-25 comparisons, a Gaussian Process model converges on the optimal parameters for that user's device.

This is called **preference learning** — the model learns a user's preferences from pairwise comparisons rather than absolute ratings.

### 12.3 The Replay Architecture
The key insight: record one reference stroke from the user, then replay it through different configs rather than asking the user to draw twice. This isolates the parameter variable cleanly.

```
1. User draws 3 reference strokes (slow, medium, fast)
   → raw InputPoints are saved (NOT just the outline)
   
2. System renders Stroke A = replay(reference, config_A)
   System renders Stroke B = replay(reference, config_B)
   
3. User picks A or B
   
4. GP model updates its belief about the 7D parameter space
   
5. Repeat 20 times → converge on optimal config
   
6. Save config to device profile JSON
```

Note: this requires the raw `InputPoints` to be stored during calibration (not just the outline). The Rust engine needs a `replay_stroke(raw_points, config) -> outline` API specifically for the calibration system.

### 12.4 The Calibration UX
**First launch:**
"Welcome to Sushi Canvas. Draw a few strokes to calibrate for your device."
- 3 reference strokes are recorded
- 20 A/B questions shown (takes ~2 minutes)
- Optimal config saved to `~/.sushi-canvas/device_profile.json`
- Never asked again unless input device changes

**Device change detection:**
When a different `pointerType` is detected (switching from mouse to stylus), user is offered "Recalibrate for this device."

**Per-device profiles:**
Different profiles stored for `mouse`, `touch`, `pen` — switching devices loads the corresponding profile automatically.

### 12.5 Implementation Stack
- **Python backend** — runs the Bayesian optimization loop using `scikit-optimize` or `optuna`
- **Rust WASM** — exposes `replay_stroke(raw_points, config) -> outline`
- **Svelte** — `Calibration.svelte` A/B comparison UI with two side-by-side canvases
- **Storage** — winning config saved via Python backend file I/O

---

## 13. Phased Roadmap

### Phase 0 — Current State (Complete)
✅ Sushi Notes base app with text, todo, code, latex blocks  
✅ File tree, search, RAG, AI sidebar  
✅ Block and note linking  
✅ Sushi Canvas standalone app with full drawing engine  
✅ Viewport pan/zoom, gesture input  
✅ Fix all known rendering bugs (bubbles, black holes, end caps)  

---

### Phase 1 — Canvas as Second Tab in Sushi Notes
**Goal:** Get Canvas living inside the Sushi Notes app without breaking anything.

**Tasks:**
- Move `canvas-engine` Rust crate into the Sushi Notes workspace
- Update root `Cargo.toml` to include `canvas-engine` as a member
- Update `vite.config.js` in Sushi Notes with the `canvas-engine` alias
- Add a second nav rail tab in Sushi Notes
- The Canvas tab renders the existing Canvas Svelte components in full-screen
- No data integration yet — Canvas saves to its own files independently
- Validate that the WASM build works inside the Sushi Notes build pipeline

**Success criteria:** Sushi Notes launches, user can switch between Notes tab and Canvas tab, draw something, save it, and the notes side is completely unaffected.

---

### Phase 2 — Select Tool in Sushi Canvas
**Goal:** Complete the core drawing toolset.

**Tasks:**
- Rust: add `selected_ids: HashSet<u64>` to engine
- Rust: `hit_test_point`, `hit_test_marquee` methods
- Rust: `commit_transform` with translate/scale/rotate relative to selection center
- Rust: `delete_selected`, `duplicate_selected`
- Rust: `TransformStrokes` and `DuplicateStrokes` history entries
- JS: pointer state machine for select mode (marquee, dragging, resizing, rotating)
- JS: two-phase transform (60fps visual JS → single commit to Rust on release)
- JS: selection bounding box with 8 resize handles and rotate handle
- JS: marching ants marquee animation
- Keyboard: Delete, Ctrl+D, Arrow keys, Escape
- Toolbar: "select" button

---

### Phase 3 — Canvas Block in Sushi Notes
**Goal:** A canvas can be embedded in a note as a first-class block.

**Tasks:**
- Add `canvas` block type to `note_schema.py`
- Create `CanvasBlock.svelte` component
- Focus/blur behavior: thumbnail when blurred, full canvas when focused
- Page size picker: A4 default, presets, custom
- Canvas save flow: `pyInvoke("save_canvas_block")` on blur
- Python backend: `save_canvas_block`, `load_canvas_block` commands
- Thumbnail generation on save
- `.resources` folder creation and management per note
- Register in `MainArea.svelte` block renderer
- Keyboard shortcut scoping: canvas shortcuts active only when canvas is focused

---

### Phase 4 — Infinite Canvas as Vault File Type
**Goal:** `.jcanvas` files are first-class citizens in the vault.

**Tasks:**
- Add `.jcanvas` to `FileIndex` table alongside notes
- `VaultService` methods for CRUD on canvas files
- `filesys.py` functions: `create_canvas`, `save_canvas`, `load_canvas`, `delete_canvas`
- IPC commands: `create_canvas_cmd`, `open_canvas`, `update_canvas`, `delete_canvas_cmd`
- Sidebar: `.jcanvas` files appear in file tree with canvas icon
- Main area: opening a canvas file shows full-screen canvas view (not block editor)
- Background pattern system: dots, grid, lines, custom tile
- `Cargo.toml` and `vite.config.js` already set up from Phase 1

---

### Phase 5 — Text Tool and Image Import
**Goal:** Canvas blocks become more than just ink.

**Tasks:**
- Text tool: click to place text object, font/size/color picker, editable
- Text objects stored in `text_objects: Vec<TextObject>` in canvas data
- Select tool integration: text objects are selectable, resizable, moveable
- Image import: drag-and-drop onto canvas
- Image stored in `.resources`, referenced by UUID
- Image objects selectable, resizable
- Crop tool (stretch goal)

---

### Phase 6 — Straight Line / Shape Recognition
**Goal:** Make diagrams and structured drawings pleasant to create.

**Tasks:**
- Shift+draw: constrain to straight line (angle snapping at 45° increments)
- Hold-to-recognize: 800ms hold after completing a closed shape triggers recognition
- Shape classifier: detect circle, rectangle, triangle, arrow, line
- Implemented in Rust (pure geometry, no ML needed for basic shapes)
- User confirms or dismisses replacement
- Shape objects stored separately from freehand strokes — remain editable as shapes

---

### Phase 7 — PDF Viewer and Annotation Canvas
**Goal:** Sushi can open and annotate PDFs.

**Tasks:**
- `pdfium-render` WASM crate added to workspace
- Python backend: `open_pdf` command reads bytes, passes to WASM
- PDF page renderer: bitmap output to `<canvas>` Layer 1
- Character bounding box extraction via `FPDFText_GetCharBox`
- Layer 2: hit testing component using char bbox map
- Layer 3: Sushi Canvas annotation overlay (finite mode, page-locked)
- Tool switching: pointer events routed to correct layer via CSS `pointer-events`
- PDF UUID assignment on import
- Per-page annotation sidecar files in `.resources`
- `VaultService` handling for PDF files in the file tree

---

### Phase 8 — Canvas Snippets and Deep Linking
**Goal:** Canvas regions can be embedded in notes and navigated back to.

**Tasks:**
- Region select tool in all canvas modes
- Snapshot rendering from canvas/PDF region
- `canvas-snippet` block type in the note schema
- Snippet update modes: auto-silent, notify, manual
- Change detection: on every canvas save, check referencing snippets
- Thumbnail regeneration pipeline
- Deep link navigation: click snippet → open source and highlight region
- Broken link handling: source deleted dialog
- Backlink recording in snippet block data

---

### Phase 9 — ML Calibration System
**Goal:** Sushi Canvas feels perfectly tuned for every device and user.

**Tasks:**
- Rust: `replay_stroke(raw_points, config) -> outline` WASM method
- Python: Bayesian optimization loop using `scikit-optimize`
- Python: device profile storage in `~/.sushi/device_profiles.json`
- Svelte: `Calibration.svelte` A/B comparison UI
- First-launch calibration flow trigger
- Device change detection and re-calibration offer
- Per-device profile loading on `pointerType` change

---

### Phase 10 — Quality of Life Polish
**Goal:** Every small thing that makes the app feel professional.

**Tasks:**
- Minimap for infinite canvas
- Zoom level HUD
- Recent colors row
- Eyedropper tool
- Stroke smoothing live slider
- Dark/light/transparent canvas background toggle
- Grid snapping
- Background pattern scale control
- Keyboard shortcut reference sheet (Ctrl+?)
- Canvas undo/redo visual feedback (brief flash on undo)

---

### Phase 11 — Knowledge Graph and Backlinks
**Goal:** Make the connections between notes, canvases, and PDFs visible and navigable.

**Tasks:**
- Backlinks tab in right panel
- Graph view: nodes for notes, canvases, PDFs; edges for all link types
- Canvas snippet references visible in graph
- PDF region references visible in graph
- Filter graph by tag, block type, date
- Click node in graph → open that file

---

### Phase 12 — Jupyter Block and Advanced Code
**Goal:** Notes can run code inline.

**Tasks:**
- `jupyter` block type
- Embedded Python kernel via the PyTauri Python process
- Cell-based execution
- Output rendering: text, images, matplotlib figures, DataFrames
- Kernel state persists within a note session
- Separate from `code` block (which is just syntax-highlighted display)

---

## 14. Open Problems & Unresolved Decisions

### 14.1 File Bundling for Export
**Problem:** A note references resources in `.resources/`. Exporting a note requires bundling the `.jnote` and all its resources into a shareable package.  
**Current thinking:** A `.sushi` archive (ZIP with manifest) generated by a packager command.  
**Unresolved:** Exact archive format, handling partial imports, handling broken resource references after import into a different vault structure.

### 14.2 PDF Annotation When PDF Is Externally Modified
**Problem:** If a PDF is modified outside Sushi (re-exported, updated version), the UUID doesn't change but the content does. Annotations may be on the wrong pages.  
**Current thinking:** Notify user, allow manual re-linking.  
**Unresolved:** Detection mechanism for "PDF content changed", page-count change handling.

### 14.3 Canvas Snippet Navigation Mode
**Problem:** When a snippet is clicked, should it open the source in the current view (replacing what's shown) or in a new panel/split view?  
**Current thinking:** User setting, default is current view for simplicity.  
**Unresolved:** The panel/split view system is not yet designed.

### 14.4 Drag Across Notebook Pages
**Problem:** In multi-page notebook mode, the user should be able to drag a canvas object past a page boundary and have it move to the adjacent page.  
**Current thinking:** Multiple implementation options, will be prototyped to find what feels best.  
**Unresolved:** Exact UX — does the object appear on both pages during drag? How does the next page appear during drag?

### 14.5 Continuous vs Separate Pages in Notebook Mode
**Problem:** Notebook mode has two sub-modes: separate pages (each page is its own canvas block) and continuous scroll (one long canvas with optional visible page lines).  
**Current thinking:** Both supported, separate pages is default.  
**Unresolved:** In continuous mode with visible page lines, what happens when a stroke crosses a page line?

### 14.6 OCR / Handwriting Recognition
**Problem:** Converting handwritten strokes to text is a major feature for a notes app but is architecturally complex.  
**Current thinking:** Defer entirely — research, experiment, then implement as a later phase.  
**Unresolved:** Everything. Engine choice, server vs local, accuracy requirements, UX for corrections.

### 14.7 Multi-Vault Support
**Problem:** Current architecture has a single vault. Power users often have multiple vaults (personal, work, projects).  
**Current thinking:** Not in current scope.  
**Unresolved:** Whether vault switching is a setting or whether multiple vaults can be open simultaneously.

---

## 15. Tech Stack Reference

### 15.1 Sushi Notes Stack
| Layer | Technology | Version |
|---|---|---|
| Desktop Shell | Rust / Tauri | v2 |
| Backend Logic | Python | 3.x |
| IPC Bridge | tauri-plugin-pytauri-api | 0.8.0 |
| Frontend | SvelteKit | Svelte 5 |
| Styling | TailwindCSS | v4 |
| Icons | Lucide-Svelte | — |
| Build (frontend) | Vite | 6.x |
| Build (backend) | Cargo | — |
| Python Env | uv | — |
| Search (keyword) | SQLite FTS5 | — |
| Search (semantic) | FAISS | cpu |
| Embeddings | Google Gemini API | — |
| Filesystem watch | watchdog | — |
| Data validation | pydantic | — |
| JSON streaming | ijson | — |

### 15.2 Sushi Canvas Stack
| Layer | Technology |
|---|---|
| Drawing Engine | Rust → WASM (wasm-pack, wasm-bindgen) |
| Canvas rendering | HTML Canvas 2D API |
| Frontend | SvelteKit (Svelte 5) + TypeScript |
| Serialization | serde + serde-wasm-bindgen |
| WASM build | wasm-pack |

### 15.3 Planned Additions
| Module | Technology |
|---|---|
| PDF rendering | pdfium-render (Rust → WASM) |
| ML calibration | scikit-optimize or optuna (Python) |
| Shape recognition | Pure Rust geometry (no ML) |
| OCR (future) | TBD |
| Jupyter (future) | Embedded Python kernel via PyTauri process |

### 15.4 File Types
| Extension | Contents | Owner |
|---|---|---|
| `.jnote` | Note JSON with blocks array | Sushi Notes |
| `.jcanvas` | Canvas JSON with strokes, text, images | Sushi Canvas |
| `.sushi` | Export archive (ZIP + manifest) | Packager |
| `.jcanvas` (annotation) | Per-page PDF annotation strokes | Sushi PDF |

### 15.5 Key Directories (Sushi Notes)
```
sushi/
├── src/lib/
│   ├── client/          # pyInvoke API wrappers
│   ├── components/
│   │   ├── editor/      # Block components (CanvasBlock.svelte goes here)
│   │   └── layout/      # NavRail, panels
│   ├── stores/          # Svelte writable stores
│   └── utils/
├── src-tauri/
│   └── src-python/sushi/
│       ├── vault_service.py
│       ├── commands.py   # IPC handlers
│       ├── note_schema.py
│       ├── filesys.py
│       └── cache_db.py
└── canvas-engine/        # Rust WASM crate (moved from sushi-canvas)
    └── src/
        ├── engine.rs
        ├── stroke.rs
        ├── smoother.rs
        ├── freehand.rs
        ├── history.rs
        ├── viewport.rs
        ├── eraser.rs
        └── export.rs
```

---

*This document reflects the state of the project as of the planning session. It is a living document — sections will be updated as decisions are made, problems are resolved, and phases are completed.*
