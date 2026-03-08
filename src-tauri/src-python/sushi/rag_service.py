"""
rag_service.py — RAGService lifecycle wrapper for the Sushi notes app.

This module bridges the standalone RAGPipeline (rag/commands.py) with the
PyTauri application layer. It:
  - Owns the RAGPipeline lifecycle (init / start / shutdown)
  - Exposes a thread-safe public API for IPC command handlers
  - Degrades gracefully when the API key is missing or the index is empty
  - Hooks into the VaultWatcher's file-event callback for incremental indexing

Architecture note:
  RAGService is registered with Manager.manage() alongside VaultService.
  All command handlers retrieve it via Manager.state(app_handle, RAGService).
"""

import atexit
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from sushi.logger import LogLevel, LogSource, sys_log, _DefaultLogSourceFilter

# ---------------------------------------------------------------------------
# Route all sushi.rag.* loggers through the sushi handler without going to
# the root logger.  The root logger may not have the log_source filter,
# causing KeyError every time a RAG module calls logger.info/warning/etc.
# ---------------------------------------------------------------------------


def _configure_rag_logging() -> None:
    """
    Point all sushi.rag.* loggers at the sushi logger and stop propagation
    to the root logger.  This must run after SushiLogger is initialised
    (i.e. after `from sushi.logger import sys_log` above).
    """
    sushi_logger = logging.getLogger("sushi")
    rag_root = logging.getLogger("sushi.rag")

    # Remove any handlers that might have been auto-added
    rag_root.handlers.clear()

    # Forward records to the sushi logger's handlers directly
    # by adding a handler that delegates, with the log_source filter
    _filter = _DefaultLogSourceFilter(default="RAG_ENGINE")
    for handler in sushi_logger.handlers:
        # Add filter to handler if not already present (idempotent)
        if not any(isinstance(f, _DefaultLogSourceFilter) for f in handler.filters):
            handler.addFilter(_filter)

    # Stop propagation — records will only flow via sushi logger's handlers
    rag_root.propagate = False
    rag_root.setLevel(logging.DEBUG)

    # Re-add the sushi handlers so RAG records still appear
    for handler in sushi_logger.handlers:
        if handler not in rag_root.handlers:
            rag_root.addHandler(handler)


_configure_rag_logging()


# ---------------------------------------------------------------------------
# Lazy import for the rag package — keeps startup fast even if dependencies
# are missing (shows a clear error instead of crashing on import).
# ---------------------------------------------------------------------------
try:
    from sushi.rag.commands import RAGPipeline
    from sushi.rag.schema import HyperParams, RAGConfig

    _RAG_AVAILABLE = True
except ImportError as _import_err:
    _RAG_AVAILABLE = False
    _import_err_msg = str(_import_err)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RAG_DATA_DIRNAME = ".rag_data"


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------


class RAGService:
    """
    Thread-safe lifecycle wrapper around RAGPipeline.

    Responsibilities
    ----------------
    - Initialize the pipeline from config files located in config_dir.
    - Start / stop the background IndexerDaemon.
    - Expose query(), build_index(), status(), and on_note_saved() to callers.
    - Degrade gracefully when the Google API key is absent.

    Thread safety
    -------------
    All public methods acquire _lock before touching _pipeline, ensuring that
    concurrent IPC calls from different Tauri threads don't corrupt state.
    """

    def __init__(self, vault_path: Path, config_dir: Path) -> None:
        self.vault_path = Path(vault_path)
        self.config_dir = Path(config_dir)
        self._lock = threading.Lock()
        self._pipeline: Optional[RAGPipeline] = None
        self._enabled = False
        self._error_message = ""
        self._file_index = None  # Set later via set_file_index()

        if not _RAG_AVAILABLE:
            self._error_message = (
                f"RAG dependencies not installed: {_import_err_msg}. Run: uv sync"
            )
            sys_log.log(LogSource.SYSTEM, LogLevel.WARNING, self._error_message)
            return

        # Try to build the pipeline; catch misconfiguration early.
        try:
            config_path = self.config_dir / "rag_config.json"
            hyperparams_path = self.config_dir / "rag_hyperparams.json"
            data_dir = self.vault_path / _RAG_DATA_DIRNAME

            config = self._resolve_config(config_path)

            if not config.google_api_key:
                self._error_message = (
                    "RAG disabled: google_api_key is not set in "
                    f"{config_path} or {self.config_dir / 'google_api_key.json'}. "
                    "Edit one of those files to enable RAG features."
                )
                sys_log.log(LogSource.SYSTEM, LogLevel.WARNING, self._error_message)
                # Pipeline won't function without a key — stay disabled but don't crash.
                return

            hp = HyperParams.load(hyperparams_path)
            self._pipeline = RAGPipeline(config, data_dir, hp)
            self._enabled = True
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.INFO,
                f"RAGService initialized. Data dir: {data_dir}",
            )
        except Exception as e:
            self._error_message = f"RAGService init failed: {e}"
            sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, self._error_message)
            self._enabled = False

    def set_file_index(self, file_index) -> None:
        """Store a reference to VaultService's FileIndex for note title lookups."""
        self._file_index = file_index

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_config(config_path: Path) -> "RAGConfig":
        """
        Load RAGConfig from config_path, then check for an api-key override.

        Key resolution order (first non-empty wins):
          1. google_api_key field in rag_config.json
          2. google_api_key field in google_api_key.json (same directory)

        This lets the user keep their key in a separate file that is easier
        to gitignore without touching rag_config.json.
        """
        config = RAGConfig.load(config_path)

        if not config.google_api_key:
            key_file = config_path.parent / "google_api_key.json"
            if key_file.exists():
                import json

                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        key_data = json.load(f)
                    key = key_data.get("google_api_key", "")
                    if key:
                        config.google_api_key = key
                        sys_log.log(
                            LogSource.SYSTEM,
                            LogLevel.INFO,
                            "RAGService: loaded google_api_key from google_api_key.json",
                        )
                except Exception as e:
                    sys_log.log(
                        LogSource.SYSTEM,
                        LogLevel.WARNING,
                        f"RAGService: could not read google_api_key.json: {e}",
                    )

        return config

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background indexer daemon (if enabled)."""
        if not self._enabled or self._pipeline is None:
            return
        try:
            self._pipeline.start_daemon()
            # Register a clean shutdown hook so the FAISS index is saved even
            # if the process exits unexpectedly (e.g. Ctrl+C in dev mode).
            atexit.register(self.stop)
            sys_log.log(LogSource.SYSTEM, LogLevel.INFO, "RAG IndexerDaemon started.")
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM, LogLevel.ERROR, f"Failed to start RAG daemon: {e}"
            )

    def stop(self) -> None:
        """Graceful shutdown: stop daemon, save FAISS index, close DB."""
        with self._lock:
            if self._pipeline is None:
                return
            try:
                self._pipeline.shutdown()
                sys_log.log(
                    LogSource.SYSTEM, LogLevel.INFO, "RAGService shut down cleanly."
                )
            except Exception as e:
                sys_log.log(
                    LogSource.SYSTEM, LogLevel.ERROR, f"RAGService shutdown error: {e}"
                )
            finally:
                self._pipeline = None
                self._enabled = False

    # ------------------------------------------------------------------
    # Public API (called by IPC command handlers and watcher hooks)
    # ------------------------------------------------------------------

    def query(self, query_text: str) -> dict[str, Any]:
        """
        Run the full six-stage RAG pipeline for a user query.

        Returns a dict that maps directly to RagQueryResponse fields.
        On error or when disabled, returns a minimal dict with rag_enabled=False.
        """
        if not self._enabled or self._pipeline is None:
            return self._disabled_response(query_text)

        with self._lock:
            try:
                result = self._pipeline.query(query_text)
                return {
                    "answer": result.answer,
                    "strategy": result.strategy,
                    "query_original": result.query_original,
                    "query_optimized": result.query_optimized,
                    "blocks_retrieved": result.blocks_retrieved,
                    "blocks_reranked": result.blocks_reranked,
                    "blocks_in_context": result.blocks_in_context,
                    "context_truncated": result.context_truncated,
                    "latency": result.latency,
                    "rag_enabled": True,
                }
            except Exception as e:
                msg = f"RAG query failed: {e}"
                sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, msg)
                return {
                    "answer": f"Error running RAG query: {e}",
                    "strategy": "error",
                    "query_original": query_text,
                    "query_optimized": query_text,
                    "blocks_retrieved": 0,
                    "blocks_reranked": 0,
                    "blocks_in_context": 0,
                    "context_truncated": False,
                    "latency": {},
                    "rag_enabled": False,
                }

    def build_index(self) -> dict[str, Any]:
        """
        Perform a full index rebuild over the entire vault.

        This is an expensive, blocking operation (Gemini API calls).
        Always call it via asyncio.to_thread() from command handlers.
        """
        if not self._enabled or self._pipeline is None:
            return {
                "status": "disabled",
                "notes_indexed": 0,
                "blocks_indexed": 0,
                "graph_nodes": 0,
                "graph_edges": 0,
                "rag_enabled": False,
                "message": self._error_message,
            }

        with self._lock:
            try:
                stats = self._pipeline.build_index(self.vault_path)
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.INFO,
                    f"RAG index built: {stats}",
                )
                return {
                    "status": stats.get("status", "ok"),
                    "notes_indexed": stats.get("notes_indexed", 0),
                    "blocks_indexed": stats.get("blocks_indexed", 0),
                    "graph_nodes": stats.get("graph_nodes", 0),
                    "graph_edges": stats.get("graph_edges", 0),
                    "rag_enabled": True,
                    "message": "",
                }
            except Exception as e:
                msg = f"Index build failed: {e}"
                sys_log.log(LogSource.SYSTEM, LogLevel.ERROR, msg)
                return {
                    "status": "error",
                    "notes_indexed": 0,
                    "blocks_indexed": 0,
                    "graph_nodes": 0,
                    "graph_edges": 0,
                    "rag_enabled": False,
                    "message": msg,
                }

    def status(self) -> dict[str, Any]:
        """Return a health snapshot of the RAG index."""
        if not self._enabled or self._pipeline is None:
            return {
                "rag_enabled": False,
                "faiss_vectors": 0,
                "tombstone_ratio": 0.0,
                "graph_nodes": 0,
                "graph_edges": 0,
                "message": self._error_message or "RAG disabled",
            }

        with self._lock:
            try:
                s = self._pipeline.status()
                return {
                    "rag_enabled": True,
                    "faiss_vectors": s.get("faiss_vectors", 0),
                    "tombstone_ratio": s.get("tombstone_ratio", 0.0),
                    "graph_nodes": s.get("graph_nodes", 0),
                    "graph_edges": s.get("graph_edges", 0),
                    "message": "ok",
                }
            except Exception as e:
                return {
                    "rag_enabled": False,
                    "faiss_vectors": 0,
                    "tombstone_ratio": 0.0,
                    "graph_nodes": 0,
                    "graph_edges": 0,
                    "message": str(e),
                }

    def on_note_saved(self, note_path: str) -> None:
        """
        Hook called by the VaultWatcher after a .jnote file is saved.

        Dispatches to the IndexerDaemon's queue — non-blocking, fire-and-forget.
        If the daemon is not running, falls back to synchronous incremental update.
        """
        if not self._enabled or self._pipeline is None:
            return

        # We intentionally do NOT hold the main lock here — the pipeline's
        # daemon/indexer has its own internal synchronization, and we want
        # this hook to return immediately so the watcher thread isn't blocked.
        try:
            self._pipeline.on_note_saved(note_path)
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.DEBUG,
                f"RAG: incremental index queued for {note_path}",
            )
        except Exception as e:
            sys_log.log(
                LogSource.SYSTEM,
                LogLevel.WARNING,
                f"RAG: incremental index hook failed for {note_path}: {e}",
            )

    # ------------------------------------------------------------------
    # Search API (Tier 1 fast + Tier 2 deep)
    # ------------------------------------------------------------------

    def search_fast(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Tier 1 — fast keyword search.

        Returns up to `limit` results combining:
          1. Note title matches from FileIndex (LIKE query)
          2. Block content matches from RAGDatabase FTS5

        No embedding API calls — pure SQLite, sub-10ms.
        """
        results: list[dict[str, Any]] = []
        seen_note_ids: set[str] = set()

        # ── 1. Note title matches (from FileIndex / cache_db) ────────────
        if self._file_index is not None:
            try:
                all_notes = self._file_index.get_all_notes()
                query_lower = query.lower()
                for note_meta in all_notes:
                    if query_lower in note_meta.note_title.lower():
                        results.append(
                            {
                                "result_type": "note",
                                "note_id": note_meta.note_id,
                                "note_title": note_meta.note_title,
                                "block_id": None,
                                "block_snippet": None,
                                "score": 1.0,
                            }
                        )
                        seen_note_ids.add(note_meta.note_id)
                        if len(results) >= limit:
                            break
            except Exception as e:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Search: title lookup failed: {e}",
                )

        # ── 2. Block content matches (FTS5 from RAG database) ────────────
        if len(results) < limit and self._pipeline is not None:
            try:
                fts_rows = self._pipeline.db.fts_search(query, limit=limit * 3)
                for row in fts_rows:
                    note_id = row["note_id"]
                    # If we already have this note from title match, skip
                    if note_id in seen_note_ids:
                        continue

                    # Resolve note title from FileIndex
                    note_title = self._resolve_note_title(note_id)
                    snippet = self._strip_markdown(row["content"])[:120]

                    results.append(
                        {
                            "result_type": "block",
                            "note_id": note_id,
                            "note_title": note_title,
                            "block_id": row["block_id"],
                            "block_snippet": snippet,
                            "score": abs(row["fts_score"])
                            if "fts_score" in row.keys()
                            else 0.0,
                        }
                    )
                    seen_note_ids.add(note_id)

                    if len(results) >= limit:
                        break
            except Exception as e:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.WARNING,
                    f"Search: FTS5 search failed: {e}",
                )

        return results[:limit]

    def search_deep(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Tier 2 — deep semantic search via FAISS.

        Embeds the query using the Gemini API, then searches the FAISS index
        for the most similar blocks. ~200-600ms latency due to API call.
        """
        if not self._enabled or self._pipeline is None:
            return []

        results: list[dict[str, Any]] = []
        seen_note_ids: set[str] = set()

        with self._lock:
            try:
                # FAISS semantic search
                semantic_hits = self._pipeline.embedding_manager.search(
                    query, k=limit * 3
                )

                for block_id, score in semantic_hits:
                    block = self._pipeline.db.get_block(block_id)
                    if block is None:
                        continue

                    note_id = block["note_id"]
                    if note_id in seen_note_ids:
                        continue

                    note_title = self._resolve_note_title(note_id)
                    snippet = self._strip_markdown(block["content"])[:120]

                    results.append(
                        {
                            "result_type": "block",
                            "note_id": note_id,
                            "note_title": note_title,
                            "block_id": block_id,
                            "block_snippet": snippet,
                            "score": round(float(score), 4),
                        }
                    )
                    seen_note_ids.add(note_id)

                    if len(results) >= limit:
                        break

            except Exception as e:
                sys_log.log(
                    LogSource.SYSTEM,
                    LogLevel.ERROR,
                    f"Search deep failed: {e}",
                )

        return results[:limit]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_note_title(self, note_id: str) -> str:
        """Look up a note title from FileIndex, falling back to 'Untitled'."""
        if self._file_index is not None:
            try:
                meta = self._file_index.get_metadata(note_id)
                if meta:
                    return meta.note_title
            except Exception:
                pass
        return "Untitled Note"

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove common markdown syntax for cleaner plain-text snippets."""
        import re as _re

        text = _re.sub(r"#{1,6}\s+", "", text)  # headings
        text = _re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
        text = _re.sub(r"\*(.+?)\*", r"\1", text)  # italic
        text = _re.sub(r"~~(.+?)~~", r"\1", text)  # strikethrough
        text = _re.sub(r"`(.+?)`", r"\1", text)  # inline code
        text = _re.sub(r"^\s*[-*+]\s+", "", text, flags=_re.MULTILINE)  # list markers
        text = _re.sub(r"^\s*>\s+", "", text, flags=_re.MULTILINE)  # blockquotes
        text = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
        text = _re.sub(r"\n{2,}", " ", text)  # multiple newlines
        return text.strip()

    def _disabled_response(self, query_text: str) -> dict[str, Any]:
        return {
            "answer": (
                "RAG is not available. "
                + (self._error_message or "Please check your rag_config.json.")
            ),
            "strategy": "disabled",
            "query_original": query_text,
            "query_optimized": query_text,
            "blocks_retrieved": 0,
            "blocks_reranked": 0,
            "blocks_in_context": 0,
            "context_truncated": False,
            "latency": {},
            "rag_enabled": False,
        }
