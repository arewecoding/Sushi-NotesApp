---
trigger: glob
globs: **/*.py
---

# Python Backend Architecture & Code Quality

You are operating on the Python backend of the Sushi application. Strictly adhere to the following constraints when generating, refactoring, or modifying Python code.

## 1. Service Layer Architecture
* **Strict Segregation:** All business logic lives in `*_service.py` classes. 
* **Thin Handlers:** IPC command handlers (in `commands.py` interfacing with the PyTauri bridge) must remain thin. The flow is strictly: validate payload -> call service method -> return envelope. Zero business logic is allowed in handlers.
* **Single Instantiation:** Services are instantiated exactly once and injected. Never instantiate a service inside a command handler or another service method.
* **Domain Ownership:** Each service owns exactly one domain (e.g., `VaultService` owns the file tree and SQLite/vector indexing, `BookService` owns `.jbook` files, `PDFService` owns rendering/annotation).
* **No Cross-Talk:** Services do not call each other directly. If cross-domain coordination is required (e.g., GraphRAG queries needing file system access), it must happen in the command handler or a dedicated coordinator.
* **Synchronous Default:** Service methods are synchronous unless they perform I/O. Do not make methods `async` by default.

## 2. Data Layer & I/O
* **Centralized I/O:** All file I/O must route through `filesys.py` utility functions (e.g., `atomic_write`, `read_json`). Never call `open()` directly inside a service.
* **Mandatory Migrations:** All deserialized data must run through a migration function before use (e.g., `migrate_canvas(data)`, `migrate_book(data)`). Never skip this pipeline.
* **Strict Typing:** Use Pydantic models for all IPC payloads and responses. Never use raw dictionaries for command inputs or outputs.

## 3. Error Handling
* **Containment:** Every command handler must wrap its body in a `try/except` block. Exceptions must never escape a handler to crash the IPC process.
* **Standardized Responses:** Use `ok(data)` or `err(code, message)` imported from `models.py` for all responses. Do not return raw dicts or throw errors over the bridge.
* **Constant Codes:** Error codes must be defined as string constants in `models.py`. Do not scatter inline string error codes across different files.

## 4. Logging Standards
* **Initialization:** Every service file must declare `log = structlog.get_logger(__name__)` at the module level.
* **Granularity:** Log at the service level (method entry for significant operations, and always log errors). Never log inside loops, per-point hot paths, or intensive search algorithms (like A* traversals).
* **Structured Keys:** Log keys must be `snake_case` nouns, not full sentences.
    * **Good:** `log.info("canvas_saved", canvas_id=123, stroke_count=45)`
    * **Bad:** `log.info("Saved canvas successfully")`