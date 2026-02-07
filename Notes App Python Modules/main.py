import sys
import time
import types
from pathlib import Path

# ==========================================
# 1. BOOTSTRAP: FIX THE NAMESPACE (THE FIX)
# ==========================================
# This tricks Python into thinking your current folder is the 'tauri_app' package.
if "tauri_app" not in sys.modules:
    tauri_package = types.ModuleType("tauri_app")
    sys.modules["tauri_app"] = tauri_package


def patch_module(module_name):
    try:
        __import__(module_name)
        module = sys.modules[module_name]
        sys.modules[f"tauri_app.{module_name}"] = module
        setattr(tauri_package, module_name, module)
    except ImportError as e:
        print(f"CRITICAL ERROR: Could not load {module_name}.py: {e}")
        sys.exit(1)


# Patch dependencies in order
patch_module("logger_service")
patch_module("ipc_models")
patch_module("note_schema")
patch_module("cache_db")
patch_module("block_factory")
patch_module("filesys")

# ==========================================
# 2. DEBUGGER SETUP
# ==========================================
try:
    import pydevd_pycharm

    print("Attempting to connect to PyCharm Debug Server on port 5678...")
    # suspend=True makes the script wait for you to press 'Resume' in PyCharm
    pydevd_pycharm.settrace('localhost', port=5678, stdout_to_server=True, stderr_to_server=True, suspend=True)
    print("Debugger connected successfully!")
except ConnectionRefusedError:
    print("WARNING: PyCharm Debug Server is not running. Resume execution without debugger.")
except ImportError:
    print("WARNING: pydevd-pycharm not installed. Skipping debugger.")

# ==========================================
# 3. APP LOGIC
# ==========================================
from active_state import VaultService

# UPDATE THIS PATH TO YOUR REAL FOLDER
NOTES_DIRECTORY = Path("C:/Users/ADMIN/Development/PyTauri/project sushi sandbox-vault/")


def main():
    print(f"--- 0. System Startup ---")

    if not NOTES_DIRECTORY.exists():
        try:
            NOTES_DIRECTORY.mkdir(parents=True, exist_ok=True)
            print(f"Created temporary vault at {NOTES_DIRECTORY}")
        except:
            print(f"ERROR: Cannot create vault at {NOTES_DIRECTORY}")
            return

    # Initialize Service
    print(f"--- 1. Initializing VaultService for: {NOTES_DIRECTORY} ---")
    vault_service = VaultService(NOTES_DIRECTORY)
    vault_service.start()

    time.sleep(1.0)  # Wait for FS scan
    print("Service started and DB populated.\n")

    # Get Notes
    all_notes = vault_service.db.get_all_notes()

    # If no notes, create one automatically
    if not all_notes:
        print("No notes found in the vault! Creating a test note...")
        # This calls the method we just added to active_state.py
        new_note = vault_service.create_note("Debug Note")
        print(f"Created new note: {new_note.note_id}")
        # Refresh list
        all_notes = vault_service.db.get_all_notes()

    # Select Note
    print("--- 2. Available Notes ---")
    for index, note_meta in enumerate(all_notes):
        print(f"[{index}] {note_meta.note_title} (ID: {note_meta.note_id})")

    try:
        # Auto-select 0 if running inside debugger console without interaction
        if not sys.stdin.isatty():
            choice = 0
        else:
            choice_input = input("\nEnter note number (or 'q'): ")
            if choice_input == 'q': return
            choice = int(choice_input)
        selected_meta = all_notes[choice]
    except:
        print("Invalid selection, defaulting to 0")
        selected_meta = all_notes[0]

    print(f"\n--- 3. Opening Note: {selected_meta.note_title} ---")
    active_note = vault_service.get_or_open_note(selected_meta.note_id)

    if not active_note:
        print("Failed to open note.")
        vault_service.stop()
        return

    # Display Blocks
    current_blocks = active_note.note_obj.blocks
    print(f"Successfully loaded {len(current_blocks)} blocks.")
    for block in current_blocks:
        print(f" - [{block.type}] {block.data.get('content', '')[:40]}...")

    # Add Block
    print("\n--- 4. Simulating User Edit ---")
    active_note.add_block(block_type="text", content=f"Debug Block {time.strftime('%H:%M:%S')}")
    print(f"Block added! Dirty state: {active_note.is_dirty}")

    print("\n--- 5. Waiting for Auto-Save... ---")
    time.sleep(3.5)

    vault_service.stop()
    print("Test complete.")


if __name__ == "__main__":
    main()