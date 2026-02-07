# PyTauri Complete Documentation (Svelte Edition)

## Table of Contents
1. [Getting Started](#1-getting-started)
2. [Using PyTauri (Configuration)](#2-using-pytauri-configuration)
3. [IPC: Python ↔ JavaScript](#3-ipc-python--javascript)
4. [Advanced IPC Patterns](#4-advanced-ipc-patterns)
5. [Async & Threading Models](#5-async--threading-models)
6. [Multiprocessing](#6-multiprocessing)
7. [Generating TypeScript Clients (Svelte Integration)](#7-generating-typescript-clients-svelte-integration)
8. [Using Tauri Plugins](#8-using-tauri-plugins)
9. [Debugging](#9-debugging)
10. [Building: Standalone Application](#10-building-standalone-application)
11. [Building: Standalone with Cython Security](#11-building-standalone-with-cython-security)
12. [Building: Wheel & Sdist](#12-building-wheel--sdist)

---

## 1. Getting Started

### Prerequisites
* **Rust**: Install via `rustup`.
* **Python**: Version 3.9 or higher.
* **Node.js**: For the frontend.
* **uv**: A fast Python package manager (recommended).
    ```bash
    pip install uv
    ```
* **Tauri CLI**:
    ```bash
    cargo install tauri-cli --version "^2.0.0" --locked
    ```

### Creating a New Project
You can create a project using the official template or manually.

**Method A: Using `create-pytauri-app` (Recommended)**
```bash
uv tool run create-pytauri-app
# Follow prompts. Select "Svelte" when asked for the frontend framework.

```

**Method B: Using `create-tauri-app` (Standard)**

```bash
pnpm create tauri-app
# 1. Project name: my-app
# 2. Identifier: com.my-app
# 3. Frontend language: TypeScript / JavaScript
# 4. Package manager: pnpm
# 5. UI Template: Svelte

```

After creating the generic Tauri app, you must add PyTauri manually (see Section 2).

---

## 2. Using PyTauri (Configuration)

If you created a vanilla Tauri app, follow these steps to integrate Python.

### 1. Python Project Structure

Inside your `src-tauri` folder, create a generic Python project structure (e.g., using `hatch`, `poetry`, or `setuptools`).

* Create a `pyproject.toml`.
* Create a `python/` directory for your source code.

**Example `pyproject.toml`:**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tauri-app"
version = "0.1.0"
dependencies = ["pytauri"]

[tool.hatch.build.targets.wheel]
packages = ["python/tauri_app"]

```

### 2. Configure `Cargo.toml`

Add `pytauri` to your Rust dependencies.

```toml
[dependencies]
pytauri = { version = "0.2.0" }
# If you need the macros:
pytauri-macros = { version = "0.2.0" }

```

### 3. Rust Entry Point (`main.rs` / `lib.rs`)

Modify your Tauri builder to initialize PyTauri.

```rust
use pytauri::{App, PyTauriBuilder};

fn main() {
    let app = App::default(); // Initialize Python
    
    tauri::Builder::default()
        .plugin(tauri_plugin_pytauri::init(app)) // Add the plugin
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

```

---

## 3. IPC: Python ↔ JavaScript

Communication happens via `tauri-plugin-pytauri`.

### 1. Define Python Commands

In your Python package (e.g., `src-tauri/python/tauri_app/__init__.py`):

```python
from pytauri import Commands, TauriConfig

# Define your configuration
config = TauriConfig()

# Create commands container
commands = Commands()

# Define a command
@commands.command()
def greet(name: str) -> str:
    return f"Hello, {name}!"

```

### 2. Frontend Invocation (Basic JS)

*Note: For Svelte, see Section 7 for the Type-Safe method.*

Without type generation, you invoke commands like this:

```javascript
import { invoke } from '@tauri-apps/api/core';

invoke('plugin:pytauri|greet', { name: 'World' })
  .then(console.log)
  .catch(console.error);

```

**Important:** The command string must be prefixed with `plugin:pytauri|`.

---

## 4. Advanced IPC Patterns

PyTauri supports generic types and Pydantic models for complex data exchange.

### Pydantic Models

You can use Pydantic models as arguments and return types. PyTauri handles the JSON serialization automatically.

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int

@commands.command()
def process_user(user: User) -> bool:
    print(f"Processing {user.name}")
    return True

```

### Error Handling

Raise exceptions in Python, and they will be rejected Promises in JavaScript.

```python
@commands.command()
def risky_command():
    raise ValueError("Something went wrong")

```

---

## 5. Async & Threading Models

PyTauri allows you to choose how Python commands are executed regarding the event loop.

### Sync vs Async Commands

* **`def func()` (Sync)**: Runs in a separate thread pool. Does *not* block the Tauri main thread. Good for CPU-bound tasks.
* **`async def func()` (Async)**: Runs on the Python `asyncio` event loop. Good for I/O bound tasks (DB queries, network requests).

**Example:**

```python
import asyncio

@commands.command()
async def fetch_data():
    await asyncio.sleep(1) # Non-blocking sleep
    return "Data fetched"

```

### Configuring the Event Loop

You can customize the `asyncio` loop policy if needed, though the default usually works fine for standard apps.

---

## 6. Multiprocessing

Python's `multiprocessing` module has caveats when bundled.

### Spawn Methods

* **Linux (Fork)**: Default. Generally works but can be tricky with UI frameworks.
* **Windows/macOS (Spawn)**: Requires strict entry point protection.

### Usage in PyTauri

If using `multiprocessing`, you must call `freeze_support()` immediately.

```python
import multiprocessing
from pytauri import App

if __name__ == '__main__':
    multiprocessing.freeze_support()
    # Initialize app...

```

**Note:** When building standalone executables, ensure your multiprocessing workers can locate the embedded Python environment. PyTauri handles most of this logic if you use the provided builders.

---

## 7. Generating TypeScript Clients (Svelte Integration)

This is the recommended way to use PyTauri with Svelte. It generates a type-safe `apiClient.ts` based on your Python Pydantic models.

### Step 1: Install Generator

Inside your project root:

```bash
pnpm add json-schema-to-typescript --save-dev

```

### Step 2: Enable in Python

Modify your `Commands` initialization to enable background generation.

```python
commands = Commands(
    experimental_gen_ts_background=True # Generates TS on app startup
)

```

### Step 3: Run Dev Server

```bash
pnpm tauri dev

```

PyTauri will generate `src/client/apiClient.ts` and `_apiTypes.d.ts`.

### Step 4: Svelte Usage

In your `.svelte` files, import the functions directly.

**`src/routes/+page.svelte` (or `App.svelte`)**

```html
<script lang="ts">
  // Import the generated client
  // Ensure the path points to where PyTauri generated the file (usually src/client)
  import { greet } from "../client/apiClient";

  let name = "";
  let message = "";

  async function handleGreet() {
    try {
      // Full autocomplete and type checking available here!
      message = await greet({ name: name });
    } catch (e) {
      console.error(e);
    }
  }
</script>

<main>
  <input bind:value={name} placeholder="Enter your name" />
  <button on:click={handleGreet}>Greet Me</button>
  <p>{message}</p>
</main>

```

### Handling Channels

If passing a `Channel` from Svelte to Python, you must use `.toJSON()` due to type mismatches.

```typescript
import { Channel } from "@tauri-apps/api/core";
import { stream_data } from "../client/apiClient"; // Generated command

const channel = new Channel();
channel.onmessage = (msg) => console.log(msg);

// Pass to Python
await stream_data({ 
    channel: channel.toJSON() as any // Cast if strict types complain
});

```

---

## 8. Using Tauri Plugins

You can use official Tauri plugins (like `fs`, `dialog`, `notifications`) alongside PyTauri.

1. **Add Plugin (Rust)**:
```bash
cargo tauri add notifications

```


2. **Register in `main.rs**`:
```rust
.plugin(tauri_plugin_notification::init())

```


3. **Use in Python**:
Currently, calling Tauri Rust plugins *directly* from Python is not supported. You must:
* Call the plugin from **JavaScript/Svelte**.
* Or, wrap the Rust plugin logic in a custom Rust command exposed to Python (advanced).



*Recommendation:* Keep UI/OS interactions (Dialogs, Notifications) in Svelte (JS) where possible, and keep business logic in Python.

---

## 9. Debugging

### Python Debugging (VSCode)

You can attach a debugger to the running Python process.

1. **Install `debugpy**`:
Add `debugpy` to your `pyproject.toml` dependencies.
2. **Add Debug Code**:
```python
import debugpy
# Pause execution until debugger attaches
debugpy.listen(5678)
debugpy.wait_for_client()

```


3. **VSCode Launch Config**:
```json
{
  "name": "Python: Remote Attach",
  "type": "python",
  "request": "attach",
  "connect": { "host": "localhost", "port": 5678 }
}

```



### Rust Debugging

Use the standard "CodeLLDB" extension in VSCode to debug the Rust binary wrapper.

---

## 10. Building: Standalone Application

This creates a single executable (e.g., `.exe` or binary) containing your Rust code, Frontend, and Python environment.

### 1. PyOxidizer Integration

PyTauri uses `pyoxidizer` or similar embedding strategies.
Ensure your `Cargo.toml` build dependencies are set up correctly (usually handled by the `pytauri-build` crate).

### 2. Build Command

```bash
pnpm tauri build

```

This triggers:

1. Frontend build (Svelte -> `dist/`).
2. Python build (collects dependencies).
3. Rust build (embeds everything).

The output is in `src-tauri/target/release/bundle/`.

---

## 11. Building: Standalone with Cython Security

To protect your Python source code from being easily read in the final build, you can compile it to C using Cython.

### 1. Requirements

* Cython installed in your build environment.
* A C compiler (MSVC on Windows, GCC/Clang on Linux/macOS).

### 2. Configuration

In your `pyproject.toml`, configure the build backend to use a Cython-aware hook or script.
(Note: Specific configuration depends on your build backend, e.g., `setuptools` or `hatch` custom hooks).

If using standard setuptools in `setup.py`:

```python
from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize("python/tauri_app/**/*.py"),
)

```

When `pnpm tauri build` runs, the Python code is compiled to shared libraries (`.so` / `.pyd`) instead of `.py` files, making reverse engineering significantly harder.

---

## 12. Building: Wheel & Sdist

If you want to distribute your Python logic as a library (for others to use in their Tauri apps), rather than a standalone app.

### Build Wheel (`.whl`)

Useful for distributing pre-compiled binaries on PyPI.

```bash
# Using build tool
pip install build
python -m build --wheel

```

This requires `cibuildwheel` if you have Rust extensions inside your Python package.

### Build Sdist (`.tar.gz`)

Contains the source code.

```bash
python -m build --sdist

```

Ensures all Rust source files and Python source files are included so the end-user can compile them.

