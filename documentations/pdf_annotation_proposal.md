# PDF Annotation Layer — Problem Statement & Technical Proposal

---

## Background

The goal is to build a **GoodNotes-style annotation app** on top of an existing PyTauri canvas built with Rust + WASM. The architecture involves stacking multiple layers — a PDF viewer, a text selection layer, and a drawing/annotation canvas — that switch based on the active tool.

---

## Problem Statement

### Core Problem: Inaccurate Text Bounding Boxes

When a PDF is rendered and a text layer is placed on top for selection and highlighting, the **text span widths do not match the visually rendered glyphs**. This causes:

- Highlight boxes that are wider than the actual text
- Highlights that bleed into blank areas
- Broken hit-testing for word and line selection

### Root Cause: PDF.js Dual-Pipeline Architecture

PDF.js processes a PDF through two completely separate pipelines:

1. **Canvas Renderer** — draws the PDF visually onto a `<canvas>` using the embedded font data
2. **TextLayer** — reconstructs selectable DOM `<span>` elements on top, measuring widths using a *substituted* web font via `OffscreenCanvas`, then applying a CSS `scaleX()` transform to approximate the correct width

These two pipelines do **not share the same font metrics**. The `scaleX` correction is an approximation, and it breaks in common scenarios:

| Scenario | Effect |
|---|---|
| Embedded/custom PDF fonts | Substitute font metrics diverge from rendered glyphs |
| Custom `charSpacing` / `wordSpacing` | Not fully propagated into span width calculation |
| Subpixel rendering at non-standard scales | `scaleX` drift compounds |
| OS-level font substitution differences | Inconsistent results across environments |

This is a **structural limitation** of PDF.js — not a fixable bug — because the two pipelines will always have edge cases where they disagree. The issue remains open as of 2025.

---

## Proposal

### Use `pdfium-render` Compiled to WASM

Instead of relying on PDF.js's dual-pipeline approach, use **`pdfium-render`** — Rust bindings to Google's PDFium engine — compiled to WASM. This solves the core problem architecturally because:

- The **same engine** handles both visual rendering and text coordinate extraction
- Character positions are derived from actual glyph data inside the PDF, not from CSS font approximations
- The visual bitmap and the text map are **always consistent** with each other

#### Key API: `FPDFText_GetCharBox`

This function returns the **exact bounding box of each character in PDF user-space coordinates**, directly from the glyph data. No substitution, no `scaleX`, no approximation.

---

### Proposed Layer Architecture

```
┌──────────────────────────────────────────────┐
│  Layer 3 — Your WASM Canvas (Rust)           │
│  Drawing, ink, annotations                   │
│  Highlight rendering using exact char rects  │
├──────────────────────────────────────────────┤
│  Layer 2 — Hit-testing & Selection           │
│  Per-character { char, x, y, w, h } map      │
│  Built from FPDFText_GetCharBox output       │
├──────────────────────────────────────────────┤
│  Layer 1 — pdfium-render WASM                │
│  Renders page as bitmap                      │
│  Outputs character bounding box data         │
│  (Same engine → coordinates always match)    │
└──────────────────────────────────────────────┘
```

All layers are `position: absolute` and stacked. **`pointer-events`** is toggled to switch the active layer based on the current tool — draw mode captures events on Layer 3, text selection mode on Layer 2.

---

### Implementation Flow

1. **Load PDF** — via a Tauri command that reads the file on the Rust/Python side and passes it as bytes; use `load_pdf_from_byte_slice` in pdfium-render (filesystem APIs are unavailable in WASM due to browser security model)
2. **Render page** — pdfium-render renders the page to a bitmap → displayed on a base `<canvas>` or `<img>` (Layer 1)
3. **Extract character data** — iterate over all characters on the page using `FPDFText_GetCharBox`, serialize to a flat array of `{ char, x, y, w, h }` structs
4. **Pass to WASM canvas** — your canvas layer consumes this array for all hit-testing, selection geometry, and highlight drawing (Layers 2 & 3)
5. **Tool switching** — toggle `pointer-events` on layers to switch between draw mode and text selection mode with no rendering pipeline changes

---

### Why Not PDF.js

| Concern | PDF.js | pdfium-render WASM |
|---|---|---|
| Text coordinate accuracy | Approximate (`scaleX` hack) | Exact (per-glyph from PDFium) |
| Font handling | Substitution-based | Uses embedded font data |
| Consistency of visual + text map | Two separate pipelines | Single engine |
| WASM compatibility | Runs in WebView natively | Compiles to WASM, runs in WebView |
| Integration with Rust/WASM stack | Requires JS bridge | Native Rust → fits existing stack |
| Highlight accuracy | Known structural issue | Solved at the architecture level |

---

### Caveat

When compiled to WASM, pdfium-render's filesystem-access functions are unavailable. PDFs must be loaded from bytes. In a Tauri context, this means reading the file via a Tauri command on the Rust/Python side and passing the bytes across the bridge — a straightforward one-time integration step.

---

## Summary

The text bounding box inaccuracy is not a bug that can be patched — it is a consequence of PDF.js using two independent pipelines with different font measurement systems. The correct fix is to use a single-engine solution where the renderer and the text coordinate extractor are the same process. `pdfium-render` compiled to WASM provides exactly this, integrates naturally with the existing Rust + WASM stack, and gives per-character bounding boxes that are pixel-accurate with the visual render.
