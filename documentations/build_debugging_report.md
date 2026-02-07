# PyTauri Build & Debugging Report

## Summary
Successfully built and packaged the `sushi` PyTauri application with a standalone Python environment. The application runs correctly on Windows.

## Issue Chronology

### 1. Silent Failure on Startup
**Symptom:** The installed application (`.exe`) would not open, and no error message was visible.
**Cause:** In `release` mode, Tauri/Rust hides the console window by default. If the app crashes early (e.g., Python init failure), it exits silently.
**Fix:** Temporarily commented out `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` in `src-tauri/src/main.rs` to enable the console and see errors.

### 2. Missing Python Standard Library
**Error:** `Error: Dynamic("during initializing Python core: Failed to import encodings module")`
**Cause:** The application was trying to initialize Python, but it couldn't find the Python Standard Library (Lib folder). The "bundle" step from the documentation had been missed.
**Fix:**
1.  Downloaded **Python 3.11 Standalone** (install_only_stripped) for Windows.
2.  Extracted it to `src-tauri/pyembed`.
3.  Created `src-tauri/tauri.bundle.json` to map `pyembed/python` to the installation root.
4.  Updated `src-tauri/Cargo.toml` with `[profile.bundle-release]`.
5.  Installed `sushi` dependencies into this embedded environment using `uv`.

### 3. Bundling Configuration Ignored
**Symptom:** App still failed with the same error after "fixing" the bundling.
**Cause:** We ran `pnpm tauri build` (default), which uses `tauri.conf.json`. It ignored our separate `tauri.bundle.json` file.
**Fix:** Used the specific build command to merge the configuration:
```powershell
pnpm tauri build --config="src-tauri/tauri.bundle.json" -- -- --profile bundle-release
```

### 4. Python Version Mismatch (DLL Hell)
**Error:** `AttributeError: module '_thread' has no attribute '_set_sentinel'`
**Cause:**
*   PyO3 (Rust crate) links against a `python3.dll` at build time.
*   Without explicit instruction, it linked against the **System Python** (likely Python 3.9 or 3.10) found in `%PATH%`.
*   At runtime, the app loaded our bundled **Python 3.11 Standard Library**.
*   **Result:** Python 3.9 DLL trying to read Python 3.11 code $\rightarrow$ Crash.
**Fix:** Set `$env:PYO3_PYTHON` to point explicitly to our bundled `python.exe` before building.

## Final Working Build Workflow
To build the application correctly in the future, run these commands in PowerShell:

```powershell
# 1. Point PyO3 to the bundled Python (Prevents version mismatch)
$env:PYO3_PYTHON = (Resolve-Path "src-tauri\pyembed\python\python.exe").Path

# 2. Build with bundling config and release profile
pnpm tauri build --config="src-tauri/tauri.bundle.json" -- -- --profile bundle-release
```

## Useful Links
- [Python Build Standalone Releases](https://github.com/astral-sh/python-build-standalone/releases)
- [PyTauri Documentation: Distribution](https://pytauri.github.io/pytauri/latest/tutorial/distribution/)
