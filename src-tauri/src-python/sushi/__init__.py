"""
Sushi Notes App — PyTauri Backend
==================================
Application entry point and lifecycle management.
"""

# -- Structlog and flags must be configured before any other sushi imports --
from sushi.logging_config import configure_logging
configure_logging()

from sushi.flags import load_flags, write_default_flags  # noqa: E402
load_flags()
write_default_flags()

import json  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from anyio.from_thread import start_blocking_portal  # noqa: E402
from pytauri import AppHandle, Manager, Emitter, builder_factory, context_factory  # noqa: E402

from sushi.commands import commands  # noqa: E402
from sushi.vault_service import VaultService  # noqa: E402
from sushi.rag_service import RAGService  # noqa: E402
from sushi.logger import sys_log, LogSource, LogLevel  # noqa: E402
from sushi.models import VaultReadyPayload  # noqa: E402


# ==========================================
# Configuration
# ==========================================


# Config dir: the directory containing rag_config.json and rag_hyperparams.json.
# Resolves to src-tauri/ at dev time (where the pyproject.toml lives) and to
# the bundle root in production.
_CONFIG_DIR = Path(__file__).parent.parent.parent

# Resolve vault path: first check sushi_settings.json, then env var, then default
_settings_file = _CONFIG_DIR / "sushi_settings.json"
_vault_path_str = ""

if _settings_file.exists():
    try:
        with open(_settings_file, "r", encoding="utf-8") as f:
            _settings = json.load(f)
            _vault_path_str = _settings.get("vault_path", "")
    except Exception:
        pass

if not _vault_path_str:
    _vault_path_str = os.environ.get(
        "SUSHI_VAULT_PATH",
        "C:/Users/ADMIN/Development/PyTauri/test project/test_1/sushi/sample_notes/",
    )

VAULT_PATH = Path(
    _vault_path_str
)  # Resolves to src-tauri/ at dev time (where the pyproject.toml lives) and to
# the bundle root in production.
_CONFIG_DIR = Path(__file__).parent.parent.parent


# ==========================================
# App Lifecycle
# ==========================================


def setup(app_handle: AppHandle) -> None:
    """
    Setup callback to initialize VaultService and RAGService during app startup.
    Called by PyTauri before the app window opens.
    """
    # ── 1. VaultService ─────────────────────────────────────────────────────
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, f"Setting up VaultService at: {VAULT_PATH}"
    )

    if not VAULT_PATH.exists():
        try:
            VAULT_PATH.mkdir(parents=True, exist_ok=True)
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"Created vault directory: {VAULT_PATH}",
            )
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Failed to create vault: {e}"
            )
            raise

    vault_service = VaultService(VAULT_PATH, app_handle)
    vault_service.start()

    Manager.manage(app_handle, vault_service)
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, "VaultService registered as managed state"
    )

    # ── 2. RAGService ────────────────────────────────────────────────────────
    sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Initializing RAGService...")

    rag_service = RAGService(vault_path=VAULT_PATH, config_dir=_CONFIG_DIR)
    rag_service.start()

    Manager.manage(app_handle, rag_service)
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, "RAGService registered as managed state"
    )

    # ── 2b. Wire FileIndex into RAGService for search title resolution ────
    rag_service.set_file_index(vault_service.db)
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, "RAGService: FileIndex wired for search"
    )

    # ── 3. Wire incremental-indexing hook ────────────────────────────────────
    # Non-invasively extend the watcher's callback so that every .jnote save
    # also triggers the RAG incremental indexer. VaultService is untouched.
    _original_callback = vault_service.watcher.handler.on_file_event_callback

    def _on_file_event_with_rag(path_str: str, mtime: float) -> None:
        # Always run the original VaultService logic first.
        _original_callback(path_str, mtime)

        # On note save events (not deletions/moves), notify RAG.
        if path_str.endswith(".jnote") and mtime not in (0.0, -1.0):
            rag_service.on_note_saved(path_str)

    vault_service.watcher.handler.on_file_event_callback = _on_file_event_with_rag
    sys_log.log(
        LogSource.SYSTEM,
        LogLevel.INFO,
        "RAG incremental-indexing hook wired into VaultWatcher.",
    )

    # ── 4. Signal frontend that backend is ready ─────────────────────────────
    try:
        Emitter.emit(app_handle, "vault-ready", VaultReadyPayload())
        sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "Emitted vault-ready event")
    except Exception as e:
        sys_log.log(
            LogSource.SYSTEM, LogLevel.ERROR, f"Failed to emit vault-ready: {e}"
        )


def main() -> int:
    """PyTauri application entry point."""
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(
            context=context_factory(),
            invoke_handler=commands.generate_handler(portal),
            setup=setup,
        )
        exit_code = app.run_return()
        return exit_code
