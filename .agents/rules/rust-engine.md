---
trigger: glob
globs: **/*.rs
---

### Rust / WASM Engine

**Pure Functions First**
- Any computation that doesn't need engine state is a free function in the appropriate module (`geometry.rs`, `smoother.rs`, etc.), not a method on `CanvasEngine`. The engine only has methods when it genuinely needs to mutate or read its own state.
- `replay_stroke`, `snap_to_angle`, `shape_to_outline`, `compute_bbox` — these are all free functions.

**Single Responsibility Per Module**
- `engine.rs` is a dispatcher only. It holds state and routes calls. Heavy logic lives in the module it belongs to (`selection.rs` for selection math, `shapes.rs` for recognition, etc.).
- If a method in `engine.rs` exceeds ~20 lines, it should be delegating to a module function.

**Undo History is Always Explicit**
- Every state mutation that the user can perform has a corresponding `HistoryEntry`. No silent mutations.
- Preview operations (color preview during drag, transform preview) must use dedicated `_preview` methods that explicitly do NOT push to history.
- History entries store enough data to fully reverse the operation — don't assume you can recompute it.

**Coordinate Space is Always Documented**
- Any function taking `x, y` parameters has a comment or doc string stating the coordinate space: `// canvas space` or `// screen space`.
- Rust engine methods only accept canvas-space coordinates. The JS layer is always responsible for the conversion before calling into WASM.

**No Panics in Exported Methods**
- `#[wasm_bindgen]` methods never `unwrap()`. Use `set_last_error()` and return a safe default or `Result<_, JsValue>`.
