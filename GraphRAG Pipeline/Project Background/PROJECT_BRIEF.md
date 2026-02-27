### **Project Name:** Vadapav

**Type:** AI-Augmented Desktop Note-Taking App
**Architecture:** PyTauri (Python Backend + Svelte Frontend)

#### **1. High-Level Overview**

"Vadapav" is a local-first, block-based note-taking application designed for high-performance knowledge management. It bridges a modern web-based UI (Svelte) with a powerful Python backend capable of heavy ML tasks. The app features a custom file format (`.jnote`), automated PDF ingestion via GROBID, and a local RAG (Retrieval-Augmented Generation) system for semantic search.

#### **2. Technology Stack (Strict Constraints)**

* **Frontend:** Svelte 5 (Runes), TypeScript, TailwindCSS.
* **Application Framework:** PyTauri (Tauri v2 with Python sidecar).
* **Backend Logic:** Python 3.12+.
* **Database/Search:** SQLite (with FTS5) and Vector Stores (for RAG).
* **Inter-Process Communication (IPC):** Tauri `invoke` commands (Frontend)  Python `@command` decorators.

#### **3. Core Architecture & Data Flow**

* **The Bridge:** The Svelte frontend **never** writes to the disk directly. It sends structured JSON payloads via Tauri IPC to the Python backend.
* **Threading Model:**
* *Main Thread:* Handles UI events and basic file I/O (CRUD).
* *Worker Threads:* Heavy ML tasks (GROBID PDF parsing, Vector Embedding generation) run in background threads to ensure the UI never freezes.


* **The "ActiveNote" System:** A watchdog mechanism in the backend that monitors the currently open file. It handles auto-saving, conflict resolution, and perpetual state management.

#### **4. Key Features to Implement**

1. **Note Editor:** A block-based editor (similar to Notion) that saves to a custom `.jnote` format (hybrid Markdown/JSON).
2. **Smart Ingestion:** A generic "Drag & Drop" zone that accepts PDFs. The backend triggers GROBID to parse the PDF into structured text, then indexes it for RAG.
3. **Semantic Search:** A search bar that queries both SQLite (keyword) and the Vector Store (semantic) to retrieve relevant note blocks.
4. **File System:** A custom File Explorer sidebar that visualizes the local directory structure.

#### **5. Design Style**

* **Visuals:** Minimalist, high-contrast, inspired by Terminal User Interfaces (TUI) but rendered with modern CSS.
* **Theme:** Dark mode by default.