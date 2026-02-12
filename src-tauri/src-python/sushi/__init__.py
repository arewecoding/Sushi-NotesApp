"""
Sushi Notes App — PyTauri Backend
==================================
Application entry point and lifecycle management.
"""

import os
from pathlib import Path

from anyio.from_thread import start_blocking_portal
from pytauri import AppHandle, Manager, Emitter, builder_factory, context_factory

from sushi.commands import commands  # Commands container + all handler registrations
from sushi.vault_service import VaultService
from sushi.logger import sys_log, LogSource, LogLevel
from sushi.models import VaultReadyPayload


# ==========================================
# Configuration
# ==========================================

# Vault path: configurable via environment variable, with dev default
VAULT_PATH = Path(
    os.environ.get(
        "SUSHI_VAULT_PATH",
        "C:/Users/ADMIN/Development/PyTauri/test project/test_1/sushi/sample_notes/",
    )
)


# ==========================================
# App Lifecycle
# ==========================================


def setup(app_handle: AppHandle) -> None:
    """
    Setup callback to initialize VaultService during app startup.
    Called by PyTauri before the app window opens.
    """
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, f"Setting up VaultService at: {VAULT_PATH}"
    )

    # Ensure vault directory exists
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

    # Initialize and register VaultService as managed state
    vault_service = VaultService(VAULT_PATH, app_handle)
    vault_service.start()

    Manager.manage(app_handle, vault_service)
    sys_log.log(
        LogSource.SYSTEM, LogLevel.INFO, "VaultService registered as managed state"
    )

    # Signal frontend that backend is ready
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
