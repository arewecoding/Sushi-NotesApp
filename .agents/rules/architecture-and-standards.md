---
trigger: always_on
---

### Cross-Cutting

**Layered Dependencies (enforced direction)**
```
Commands → Services → Filesys / DB
Components → Client (IPC wrappers) → [IPC bridge] → Commands
Engine (Rust) ← Client adapters ← Components
```
Dependencies only flow downward in this stack. Services never import from `commands.py`. Components never import from services directly.

**No Magic Numbers**
- Any numeric constant that isn't obviously `0`, `1`, or `2` gets a named constant: `UNDO_HISTORY_LIMIT`, `THUMBNAIL_WIDTH_PX`, `PALM_REJECT_TIMEOUT_MS`, `MIN_MARQUEE_SIZE_PX`.
- Constants live at the top of the file that owns them, or in a `constants.ts` / `constants.py` if shared.

**Feature Flags Gate New Code**
- Any feature behind a phase boundary is gated with `flag("feature_name")` on the Python side and a corresponding `FLAG_*` boolean on the Svelte side. Dead code paths are not left ungated.

**Interface Before Implementation**
- When implementing a new service, define the public method signatures and their docstrings first (inputs, outputs, side effects, errors). Only then implement the bodies. Antigravity should output the interface as a first step and wait for review before filling in bodies if the feature is non-trivial.

**Naming Conventions**
- Python: `snake_case` everywhere. Services are `NounService`. IPC commands are `verb_noun_cmd`.
- Rust: `snake_case` for functions/fields, `PascalCase` for types/enums. WASM-exported methods use the same `verb_noun` pattern as the IPC commands they correspond to.
- TypeScript: `camelCase` for functions/variables, `PascalCase` for types/interfaces. Client functions mirror the IPC command names: `saveCanvasBlock()` wraps `save_canvas_block_cmd`.
- Files mirror their primary export: `BookService` lives in `book_service.py`, `CanvasBlock.svelte` exports `CanvasBlock`.

**Project Context & Documentation**
* **Consult First:** Before drafting new code, proposing architectural changes, or implementing complex features (like GraphRAG pipelines or A* search traversals), you must read the relevant files in the `documentations/` and `ideas/` directories.
* **Align with Blueprints:** Ensure all new implementations strictly adhere to the established specifications for our PyTauri, SQLite, and vector search integrations. 
* **Do Not Hallucinate Architecture:** If a specification, data model, or workflow already exists in the documentation or ideas folders, use it. Do not invent new architectural patterns or external dependencies without explicit permission.

**Diagnostic Logging Pipeline**
* **Unified Trace Access:** All Svelte frontend logs (`console.log`, `warn`, `error`, etc.) are seamlessly intercepted and piped via IPC to the Python backend. They are chronologically interleaved with backend `sys_log` outputs and appended to `debug_trace.log` located at the project root.
* **No Manual Copy-Pasting:** Antigravity MUST NEVER ask the user to open browser DevTools or manually copy-paste console output. 
* **Autonomous Debugging:** When investigating an issue, Antigravity should independently use `view_file` or `run_command` (e.g. `tail`, `Select-String`) to read the local `debug_trace.log` file directly. 
* **Instrumentation Strategy:** When deploying temporary diagnostic instrumentation, simply inject standard `console.log` on the Svelte side, or `sys_log.log()` on the Python backend. Instruct the user to replicate the bug, and then read the `debug_trace.log` file natively to collect the results.