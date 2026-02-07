# Vadapav - Project Overview & Context

## 1. Project Identity
**Name:** Vadapav
**Type:** AI-Augmented Desktop Note-Taking App
**Core Value:** Local-first, block-based, high-performance knowledge management with TUI-inspired aesthetics.

## 2. Technology Stack
-   **Frontend Framework:** Svelte 5 (Runes mode)
-   **Language:** TypeScript
-   **Build Tool:** Vite
-   **Styling:** TailwindCSS v4 (using `@tailwindcss/postcss`)
-   **Icons:** Lucide Svelte

## 3. Project Structure
The project follows a standard Vite + Svelte structure with a component-based architecture.

```text
/
├── public/              # Static assets
├── src/
│   ├── assets/          # Images/SVGs
│   ├── lib/
│   │   └── components/
│   │       └── layout/  # Core Layout Components
│   │           ├── NavRail.svelte    # Extreme Left: App Navigation (Notes, Calendar, etc.)
│   │           ├── LeftPanel.svelte  # Left: File Explorer & Secondary Nav
│   │           ├── MainArea.svelte   # Center: Editor & Toolbar
│   │           └── RightPanel.svelte # Right: Metadata & Context
│   ├── App.svelte       # Root Layout Orchestrator
│   ├── app.css          # Global Styles (& Tailwind Entry)
│   └── main.ts          # Entry Point
├── package.json         # Dependencies & Scripts
├── postcss.config.js    # Tailwind v4 Configuration
├── tailwind.config.js   # (Legacy/Optional - v4 uses CSS config)
└── vite.config.ts       # Vite Configuration
```

## 4. Key Components Breakdown

### Layout Architecture (`src/App.svelte`)
The app uses a 4-column layout orchestrated by Flexbox/Grid:
1.  **NavRail** (`w-16`): High-level mode switching.
2.  **LeftPanel** (`w-64`): Context-specific navigation (File Tree).
3.  **MainArea** (`flex-grow`): The actual workspace (Note Editor).
4.  **RightPanel** (`w-64`): Auxiliary details (Metadata, Backlinks).

### Styling System
-   **Theme:** Dark Mode Default (`bg-neutral-900`, `text-neutral-100`).
-   **Font:** Monospace (`font-mono`) to mimic a Terminal User Interface (TUI).
-   **Design Tokens:**
    -   Backgrounds: `neutral-900` (Main), `neutral-800` (Secondary/Hover).
    -   Borders: `neutral-800` (Subtle dividers).
    -   Text: `neutral-100` (Primary), `neutral-400` (Muted).

## 5. Current State
-   **Phase:** UI Skeleton & Layout Verification.
-   **Completed:**
    -   Project scaffolding (Svelte 5 + Vite).
    -   TailwindCSS v4 implementation.
    -   Core layout components created and assembled.
-   **Next Steps:**
    -   Implement interactive File Tree logic.
    -   Build the TipTap-based Block Editor.
    -   Integrate backend (Tauri) IPC bridge.

## 6. Commands
-   **Dev Server:** `npm run dev`
-   **Build:** `npm run build`
