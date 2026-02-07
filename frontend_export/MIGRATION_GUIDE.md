# Frontend Migration Guide

This directory contains the standalone Svelte 5 frontend for the Vadapav application. Follow these instructions to integrate it into a new PyTauri project.

## Project Overview
- **Framework**: Svelte 5 (SvelteKit-like structure adapted for Tauri)
- **Styling**: TailwindCSS
- **State Management**: Local Svelte state / Stores (if applicable)
- **Build Tool**: Vite

## Prerequisites
- Node.js (Latest LTS recommended)
- pnpm (Recommended package manager)
  ```bash
  npm install -g pnpm
  ```

## Integration Instructions

1.  **Prepare the New Project**
    Ensure you have a standard PyTauri or Tauri + Svelte project structure.

2.  **Copy Files**
    Move the contents of this `frontend_export` directory into the root of your new project, overwriting existing files if necessary.
    - `src/` -> Replace/Merge with your project's `src/`
    - `static/` -> Replace/Merge with your project's `static/`
    - Config files (`package.json`, `vite.config.js`, `tailwind.config.js`, etc.) -> Merge carefully.

3.  **Install Dependencies**
    Run the installation command to fetch all node modules:
    ```bash
    pnpm install
    ```

4.  **Verify Configuration**
    - Check `vite.config.js` to ensure the Tauri settings (port, strict port, etc.) match your backend configuration.
    - Ensure `src-tauri/tauri.conf.json` (in your new project) points to the correct dist/build directory (usually `../build` or `../dist`).

5.  **Run Development Server**
    ```bash
    pnpm tauri dev
    ```

## Directory Structure
- `src/`: Contains all source code.
    - `routes/`: Main application pages/routes.
    - `lib/`: Reusable components and helper functions.
    - `app.html`: The main entry point HTML template.
- `static/`: Static assets (icons, images) served at the root path.

## Notes for AI Agents
- If you are an AI recreating this environment, prioritize `package.json` dependencies.
- The `src-tauri` side is NOT included here. You will need to set up the Rust/Python backend separately or ensure this frontend can communicate with the existing backend commands.
