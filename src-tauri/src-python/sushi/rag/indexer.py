"""
indexer.py — Incremental re-indexing engine.

Handles the full lifecycle of keeping the RAG index in sync with .jnote files:
  - Initial full index build (scan all notes)
  - Incremental updates on note save (hash-based change detection)
  - Tombstone + append strategy for FAISS
  - Scoped edge recomputation
  - Background queue processing with debounce
"""

import hashlib
import json
import logging
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from .edges import EdgeInference, extract_blocks_from_jnote, parse_jnote
from .embeddings import EmbeddingManager
from .schema import HyperParams, RAGConfig, RAGDatabase

logger = logging.getLogger(__name__)


class BlockStatus(Enum):
    """Classification of a block during incremental indexing."""

    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    NEW = "new"
    DELETED = "deleted"


def content_hash(text: str) -> str:
    """SHA-256 hash of block content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Indexer:
    """
    Main indexer that orchestrates full and incremental index builds.
    Coordinates schema, embeddings, edges, and FAISS.
    """

    def __init__(
        self,
        config: RAGConfig,
        db: RAGDatabase,
        embedding_manager: EmbeddingManager,
        edge_inference: EdgeInference,
        hp: HyperParams | None = None,
    ):
        self.config = config
        self.db = db
        self.emb = embedding_manager
        self.edges = edge_inference
        self.hp = hp or HyperParams()

    # ── Full Index Build ───────────────────────────────────────────────────

    def build_full_index(self, notes_dir: Path) -> dict[str, int]:
        """
        Scan all .jnote files in a directory and build the complete index.

        Returns stats: {notes_processed, blocks_indexed, edges_created}
        """
        jnote_files = list(notes_dir.rglob("*.jnote"))
        logger.info(f"Full index build: found {len(jnote_files)} .jnote files")

        stats = {"notes_processed": 0, "blocks_indexed": 0, "edges_created": 0}

        for file_path in jnote_files:
            try:
                result = self._index_note(file_path)
                stats["notes_processed"] += 1
                stats["blocks_indexed"] += result["blocks_indexed"]
                stats["edges_created"] += result["edges_created"]
            except Exception as e:
                logger.error(f"Failed to index {file_path}: {e}")

        # Save FAISS index to disk
        self.emb.save()
        logger.info(f"Full index complete: {stats}")
        return stats

    def _index_note(self, file_path: Path) -> dict[str, int]:
        """Index a single .jnote file (used for both full and incremental)."""
        note_path = str(file_path)
        jnote_data = parse_jnote(file_path)
        blocks = extract_blocks_from_jnote(jnote_data, note_path)

        blocks_indexed = 0
        block_ids = []
        contents = []

        for block in blocks:
            c_hash = content_hash(block["content"])

            # Upsert block into SQLite
            self.db.upsert_block(
                block_id=block["block_id"],
                note_id=block["note_id"],
                note_path=note_path,
                content=block["content"],
                block_type=block["block_type"],
                content_hash=c_hash,
            )

            block_ids.append(block["block_id"])
            contents.append(block["content"])
            blocks_indexed += 1

        # Batch embed all blocks in a single API call
        if block_ids:
            self.emb.embed_and_store_batch(block_ids, contents)

        # Infer explicit edges
        edges_created = self.edges.infer_edges_for_note(note_path)

        return {"blocks_indexed": blocks_indexed, "edges_created": edges_created}

    # ── Incremental Update ─────────────────────────────────────────────────

    def incremental_update(self, file_path: Path) -> dict[str, Any]:
        """
        Incrementally update the index for a single .jnote file.
        Uses content hashing to detect what changed.

        Returns stats about what was done.
        """
        note_path = str(file_path)
        jnote_data = parse_jnote(file_path)
        blocks = extract_blocks_from_jnote(jnote_data, note_path)
        note_id = jnote_data.get("metadata", {}).get("note_id", "")

        # Get existing block hashes from DB
        existing_hashes = self.db.get_all_block_hashes(note_id)
        current_block_ids = {b["block_id"] for b in blocks}

        stats = {
            "new": 0,
            "modified": 0,
            "deleted": 0,
            "unchanged": 0,
            "edges_updated": 0,
        }

        # Classify each block
        blocks_to_embed: list[dict] = []

        for block in blocks:
            c_hash = content_hash(block["content"])
            old_hash = existing_hashes.get(block["block_id"])

            if old_hash is None:
                # New block
                status = BlockStatus.NEW
                stats["new"] += 1
            elif old_hash != c_hash:
                # Modified block
                status = BlockStatus.MODIFIED
                stats["modified"] += 1
            else:
                # Unchanged
                status = BlockStatus.UNCHANGED
                stats["unchanged"] += 1
                continue

            # Upsert into SQLite
            self.db.upsert_block(
                block_id=block["block_id"],
                note_id=block["note_id"],
                note_path=note_path,
                content=block["content"],
                block_type=block["block_type"],
                content_hash=c_hash,
            )

            if status == BlockStatus.MODIFIED:
                # Tombstone old embedding
                self.emb.tombstone_block(block["block_id"])
                # Clear old edges
                self.edges.clear_edges_for_block(block["block_id"])

            blocks_to_embed.append(block)

        # Handle deleted blocks (in DB but not in current file)
        deleted_ids = set(existing_hashes.keys()) - current_block_ids
        for deleted_id in deleted_ids:
            self.emb.tombstone_block(deleted_id)
            self.edges.clear_edges_for_block(deleted_id)
            self.db.delete_block(deleted_id)
            stats["deleted"] += 1

        # Batch embed new/modified blocks
        if blocks_to_embed:
            embed_ids = [b["block_id"] for b in blocks_to_embed]
            embed_contents = [b["content"] for b in blocks_to_embed]
            self.emb.embed_and_store_batch(embed_ids, embed_contents)

        # Re-infer edges for the note (explicit edges)
        if blocks_to_embed or deleted_ids:
            stats["edges_updated"] = self.edges.infer_edges_for_note(note_path)

            # Infer semantic edges for changed blocks
            for block in blocks_to_embed:
                self._infer_semantic_edges_for_block(block["block_id"])

        # Check if compaction is needed
        if self.emb.should_compact():
            logger.info("Tombstone ratio exceeded threshold, triggering compaction")
            self.emb.compact()

        # Save FAISS index
        self.emb.save()

        logger.info(f"Incremental update for {file_path.name}: {stats}")
        return stats

    def _infer_semantic_edges_for_block(self, block_id: str) -> int:
        """
        Find semantically similar blocks for a single block and create edges.
        Scoped: only checks top-K nearest neighbors, not all blocks.
        """
        block_vector = self.emb.get_block_vector(block_id)
        if block_vector is None:
            return 0

        # Find top-K nearest neighbors via FAISS
        k = min(self.hp.semantic_edge_top_k, self.emb.faiss_index.total_vectors)
        if k == 0:
            return 0

        active_positions = set(self.db.get_active_faiss_positions())
        neighbors = self.emb.faiss_index.search(
            block_vector, k=k, active_positions=active_positions
        )

        if not neighbors:
            return 0

        # Gather neighbor vectors and IDs
        neighbor_ids = []
        neighbor_vectors = []
        for pos, score in neighbors:
            nid = self.db.get_block_id_for_faiss_position(pos)
            if nid and nid != block_id:
                vec = self.emb.faiss_index.index.reconstruct(pos)
                neighbor_ids.append(nid)
                neighbor_vectors.append(vec)

        if not neighbor_ids:
            return 0

        return self.edges.infer_semantic_edges(
            block_id=block_id,
            block_vector=block_vector,
            all_block_ids=neighbor_ids,
            all_vectors=np.array(neighbor_vectors, dtype=np.float32),
        )


class IndexerDaemon:
    """
    Background daemon that processes the index queue with debouncing.
    Hooks into the existing watchdog's on_save event.
    """

    def __init__(
        self,
        indexer: Indexer,
        config: RAGConfig,
        db: RAGDatabase,
        hp: HyperParams | None = None,
    ):
        self.indexer = indexer
        self.config = config
        self.db = db
        self.hp = hp or HyperParams()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background queue processor."""
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_queue_loop, daemon=True
        )
        self._worker_thread.start()
        logger.info("Indexer daemon started")

    def stop(self) -> None:
        """Stop the background queue processor."""
        self._running = False
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Indexer daemon stopped")

    def on_note_saved(self, note_path: str) -> None:
        """
        Called when a .jnote file is saved (by the app or external editor).
        Debounces and queues for re-indexing.
        """
        with self._lock:
            # Cancel any existing debounce timer for this path
            if note_path in self._debounce_timers:
                self._debounce_timers[note_path].cancel()

            # Set a new debounce timer
            timer = threading.Timer(
                self.config.indexer_debounce_seconds,
                self._enqueue_after_debounce,
                args=(note_path,),
            )
            self._debounce_timers[note_path] = timer
            timer.start()

    def _enqueue_after_debounce(self, note_path: str) -> None:
        """Called after debounce period expires. Add to the queue."""
        with self._lock:
            self._debounce_timers.pop(note_path, None)
        self.db.enqueue_note(note_path)
        logger.debug(f"Queued for re-indexing: {note_path}")

    def _process_queue_loop(self) -> None:
        """Background loop that processes the index queue."""
        while self._running:
            try:
                pending = self.db.dequeue_pending(
                    limit=self.hp.daemon_dequeue_batch_size
                )
                for item in pending:
                    try:
                        file_path = Path(item["note_path"])
                        if file_path.exists():
                            self.indexer.incremental_update(file_path)
                        self.db.mark_queue_done(item["id"])
                    except Exception as e:
                        logger.error(f"Failed to process queue item {item['id']}: {e}")
                        self.db.mark_queue_failed(item["id"])

                if not pending:
                    time.sleep(
                        self.hp.daemon_idle_sleep_seconds
                    )  # No work to do, sleep briefly
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                time.sleep(self.hp.daemon_error_backoff_seconds)  # Back off on errors
