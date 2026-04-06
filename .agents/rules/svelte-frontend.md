---
trigger: glob
globs: **/*.svelte, src/**/*.ts
---

### Svelte / Frontend

**Component Contracts**
- Every block component (`CanvasBlock.svelte`, `CanvasSnippetBlock.svelte`, etc.) accepts exactly: `block: BlockData`, `noteId: string`. It dispatches exactly: `change`, `focus`, `blur`, `delete`. No exceptions without explicit justification.
- Components do not import IPC functions directly. They call IPC through a typed client module in `src/lib/client/`. Components are not responsible for knowing command names.

**State Ownership**
- Svelte `$state()` is for UI state only (is this panel open, which tab is active, loading spinner visibility).
- Domain state (canvas strokes, note blocks, file tree) is owned by the service layer or the Rust engine. Svelte derives display data from it, doesn't own it.
- Canvas content is never in `$state()`. The engine owns it.

**IPC Layer**
- All WASM-to-Python calls go through `canvasInvoke<T>()` in the client module. Raw `pyInvoke` is never called from components.
- The client module is the only place that knows command name strings.
- All `canvasInvoke` calls are `await`-ed and errors are caught at the call site or via the central handler — never silently swallowed.

**No God Components**
- If a `.svelte` file exceeds ~250 lines, it must be split. Extract sub-components or logic modules (`*.ts` files alongside the component).
- Event handlers that exceed ~15 lines are extracted to named functions defined above the markup, not inline lambdas.