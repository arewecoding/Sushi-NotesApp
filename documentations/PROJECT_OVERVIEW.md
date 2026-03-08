# Project Overview: Sushi Notes App

## 1. Introduction
**Sushi** is a high-performance, local-first note-taking application built with **PyTauri**. It combines the performance and security of **Rust/Tauri** with the flexibility of **Python** for the backend logic, and offers a modern, reactive user interface using **SvelteKit**.

**Core Philosophy:**
- **Local-First:** All data is stored as plain JSON files (`.jnote`) on the user's disk.
- **Sidecarless:** Python is embedded directly into the Rust process memory (via `pyo3`/`pytauri`), avoiding the latency of standard sidecar subprocesses.
- **Reactive:** The app uses a file watcher to stay in sync with the filesystem in real-time.

## 2. Technology Stack

### Frontend
- **Framework:** SvelteKit (Svelte 5)
- **Language:** TypeScript
- **Styling:** TailwindCSS v4
- **Icons:** Lucide-Svelte
- **Build Tool:** Vite

### Backend (The "PyTauri" Bridge)
- **Framework:** Tauri v2
- **Core:** Rust
- **Scripting:** Python 3.x (embedded)
- **IPC:** Custom PyTauri plugin (`tauri-plugin-pytauri-api`) for frontend-to-python communication.

### Python Environment
- **Dependency Manager:** `uv` (implied by `uv.lock`) or standard pip.
- **Key Libraries:** `watchdog` (filesystem events), `pydantic` (validation), `anyio` (async I/O).

## 3. Directory Structure

```
/
├── src-tauri/               # Rust/Tauri Backend Context
│   ├── src/lib.rs           # Rust entry point (initializes Python)
│   ├── tauri.conf.json      # Tauri Configuration
│   └── ...
├── src/                     # SvelteKit Frontend
│   ├── routes/+page.svelte  # Main Entry Point
│   ├── lib/
│   │   ├── components/      # UI Components (Editor, Layout, etc.)
│   │   ├── stores/          # Svelte Stores (State Management)
│   │   └── ...
│   └── ...
├── Notes App Python Modules/# CURRENT Python Source Code
│   ├── active_state.py      # Core Logic (VaultService, ActiveNote)
│   ├── filesys.py           # Watchdog & File I/O
│   ├── note_schema.py       # Pydantic Models (JNote)
│   └── ...
├── PyTauri Backend Architecture Consultation.md  # ARCHITECTURE ROADMAP (Critical Read)
├── package.json             # Frontend Dependencies
├── Cargo.toml               # Rust Dependencies
└── ...
```

## 4. Architecture & State Management

### Current Implementation ("Monolithic Service")
*Note: The codebase currently interacts heavily with `active_state.py`.*

- **VaultService (`active_state.py`):** The "God Object" that manages:
    - **Active Notes:** In-memory representation of open files.
    - **File Watcher:** Instantiated from `filesys.py`.
    - **Database:** An in-memory SQLite index (`cache_db.py`) for sidebar navigation.
- **ActiveNote:** Representative of a single open note. Handles "Hot-Swapping" (reloading from disk if external changes occur) and "Echo Suppression" (ignoring events caused by its own saves).
- **Frontend Interfacing:** The frontend talks to Python via Tauri Commands which route to methods in `ActiveNote` or `VaultService`.

### Future Architecture ("Clean/Hexagonal")
*Refer to `PyTauri Backend Architecture Consultation.md`.*
The project is aiming to migrate to a Clean Architecture with:
- **Domain Layer:** Pure Python entities (`Note`, `Block`).
- **Infrastructure Layer:** Repositories for FileSystem and SQLite.
- **Dependency Injection:** To decouple services.
- **CQRS:** Separating Read (Sidebar) from Write (Editor) operations.
**Start generic refactoring or new features with this goal in mind.**

## 5. Key Features Implementation Details

- **Block Editor (`MainArea.svelte`):**
  - Notes are composed of "Blocks" (text, code, todo).
  - Uses a non-reactive local state `blockContents` for performance, syncing to Svelte stores only on save/change events.
  - Implements its own Drag-and-Drop system for block reordering.

- **Filesystem Sync:**
  - `filesys.py` runs a `watchdog` observer.
  - Changes on disk (e.g., from VS Code or Dropbox) trigger `on_modified` events.
  - `ActiveNote` checks the timestamp. If the change was external, it reloads the note content in real-time (Hot-Swap).

## 6. Development Setup

1.  **Install Dependencies:**
    - Frontend: `pnpm install`
    - Rust: Ensure `cargo` is installed.
    - Python: Ensure a compatible Python version is available (project uses `uv` for management).

2.  **Run Development Server:**
    ```bash
    pnpm tauri dev
    ```
    This starts the Vite server and the Tauri application window.

## 7. Useful Constraints for AI
- **OS:** Windows (Primary development environment).
- **Path Handling:** Be careful with file paths. Use `pathlib` in Python and avoid hardcoding user strings (though some exist in legacy code).
- **Concurrency:** Python runs in a separate thread from Rust but shares memory. Be mindful of the GIL and use `active_state.py`'s locking mechanisms (`threading.Lock`) when modifying state.
