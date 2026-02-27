"""
schema.py — SQLite schema, migrations, and config loader for the RAG knowledge graph.

Tables:
  - blocks:          Indexed note blocks with content hashes
  - blocks_fts:      FTS5 virtual table for keyword search
  - edges:           Relationships between blocks (explicit + inferred)
  - embeddings_meta: FAISS index position mapping with tombstone support
  - index_queue:     Queue for incremental re-indexing
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RAGConfig:
    """Configuration loaded from rag_config.json."""

    # Embedding
    embedding_provider: str = "google"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 3072

    # LLM
    llm_provider: str = "google"
    llm_model: str = "gemini-2.0-flash"

    # Reranker
    reranker_provider: str = "google"

    # API key
    google_api_key: str = ""

    # Tuning knobs
    similarity_threshold: float = 0.85
    tombstone_compaction_ratio: float = 0.20
    indexer_debounce_seconds: float = 2.0
    retrieval_top_k: int = 50
    reranker_top_k: int = 10
    astar_max_nodes: int = 100
    context_max_tokens: int = 4000

    @classmethod
    def load(cls, config_path: Path) -> "RAGConfig":
        """Load config from a JSON file, falling back to defaults for missing keys."""
        if not config_path.exists():
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HyperParams:
    """
    Fine-grained hyperparameters loaded from rag_hyperparams.json.
    These were previously hardcoded across modules.
    """

    # ── Edge weights (lower = stronger relationship = lower A* cost) ──
    edge_weight_backlink: float = 0.1
    edge_weight_same_note: float = 0.2
    edge_weight_shared_tag: float = 0.3
    edge_weight_semantically_similar: float = 0.5

    # ── Search ────────────────────────────────────────────────────────
    rrf_k: int = 60
    retrieval_overfetch_multiplier: int = 2
    faiss_overfetch_multiplier: int = 3

    # ── Reranker ──────────────────────────────────────────────────────
    reranker_temperature: float = 0.0
    reranker_content_preview_max_chars: int = 500

    # ── Router ────────────────────────────────────────────────────────
    routing_temperature: float = 0.0
    optimization_temperature: float = 0.0

    # ── LLM ───────────────────────────────────────────────────────────
    synthesis_temperature: float = 0.3

    # ── Context assembly ──────────────────────────────────────────────
    chars_per_token: int = 4
    min_remaining_chars_for_truncated_block: int = 100

    # ── Indexer ───────────────────────────────────────────────────────
    semantic_edge_top_k: int = 20
    daemon_idle_sleep_seconds: float = 1.0
    daemon_error_backoff_seconds: float = 5.0
    daemon_dequeue_batch_size: int = 5

    # ── Traversal ─────────────────────────────────────────────────────
    traversal_entry_nodes_count: int = 5
    unknown_node_heuristic_cost: float = 1.0

    # ── Evaluation ────────────────────────────────────────────────────
    judge_temperature: float = 0.0

    @property
    def edge_weights(self) -> dict[str, float]:
        """Returns the edge weight mapping for use by edges.py."""
        return {
            "backlink": self.edge_weight_backlink,
            "same_note": self.edge_weight_same_note,
            "shared_tag": self.edge_weight_shared_tag,
            "semantically_similar": self.edge_weight_semantically_similar,
        }

    @classmethod
    def load(cls, config_path: Path) -> "HyperParams":
        """Load hyperparams from JSON, supporting nested sections."""
        if not config_path.exists():
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        flat: dict = {}

        # Flatten the nested JSON into the flat dataclass fields
        if "edge_weights" in data:
            ew = data["edge_weights"]
            flat["edge_weight_backlink"] = ew.get("backlink", 0.1)
            flat["edge_weight_same_note"] = ew.get("same_note", 0.2)
            flat["edge_weight_shared_tag"] = ew.get("shared_tag", 0.3)
            flat["edge_weight_semantically_similar"] = ew.get(
                "semantically_similar", 0.5
            )

        if "search" in data:
            s = data["search"]
            flat["rrf_k"] = s.get("rrf_k", 60)
            flat["retrieval_overfetch_multiplier"] = s.get(
                "retrieval_overfetch_multiplier", 2
            )
            flat["faiss_overfetch_multiplier"] = s.get("faiss_overfetch_multiplier", 3)

        if "reranker" in data:
            r = data["reranker"]
            flat["reranker_temperature"] = r.get("temperature", 0.0)
            flat["reranker_content_preview_max_chars"] = r.get(
                "content_preview_max_chars", 500
            )

        if "router" in data:
            rt = data["router"]
            flat["routing_temperature"] = rt.get("routing_temperature", 0.0)
            flat["optimization_temperature"] = rt.get("optimization_temperature", 0.0)

        if "llm" in data:
            flat["synthesis_temperature"] = data["llm"].get(
                "synthesis_temperature", 0.3
            )

        if "context_assembly" in data:
            ca = data["context_assembly"]
            flat["chars_per_token"] = ca.get("chars_per_token", 4)
            flat["min_remaining_chars_for_truncated_block"] = ca.get(
                "min_remaining_chars_for_truncated_block", 100
            )

        if "indexer" in data:
            ix = data["indexer"]
            flat["semantic_edge_top_k"] = ix.get("semantic_edge_top_k", 20)
            flat["daemon_idle_sleep_seconds"] = ix.get("daemon_idle_sleep_seconds", 1.0)
            flat["daemon_error_backoff_seconds"] = ix.get(
                "daemon_error_backoff_seconds", 5.0
            )
            flat["daemon_dequeue_batch_size"] = ix.get("daemon_dequeue_batch_size", 5)

        if "traversal" in data:
            tr = data["traversal"]
            flat["traversal_entry_nodes_count"] = tr.get("entry_nodes_count", 5)
            flat["unknown_node_heuristic_cost"] = tr.get(
                "unknown_node_heuristic_cost", 1.0
            )

        if "evaluation" in data:
            flat["judge_temperature"] = data["evaluation"].get("judge_temperature", 0.0)

        # Filter to valid fields only
        valid = {k: v for k, v in flat.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- ── Core blocks table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blocks (
    block_id        TEXT PRIMARY KEY,
    note_id         TEXT NOT NULL,
    note_path       TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    block_type      TEXT NOT NULL DEFAULT 'text',
    content_hash    TEXT NOT NULL DEFAULT '',
    last_indexed_at TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blocks_note_id ON blocks(note_id);
CREATE INDEX IF NOT EXISTS idx_blocks_content_hash ON blocks(content_hash);

-- ── FTS5 full-text search ─────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
    block_id,
    content,
    content='blocks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS5 in sync with blocks table
CREATE TRIGGER IF NOT EXISTS blocks_ai AFTER INSERT ON blocks BEGIN
    INSERT INTO blocks_fts(rowid, block_id, content)
    VALUES (new.rowid, new.block_id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS blocks_ad AFTER DELETE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, block_id, content)
    VALUES ('delete', old.rowid, old.block_id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS blocks_au AFTER UPDATE ON blocks BEGIN
    INSERT INTO blocks_fts(blocks_fts, rowid, block_id, content)
    VALUES ('delete', old.rowid, old.block_id, old.content);
    INSERT INTO blocks_fts(rowid, block_id, content)
    VALUES (new.rowid, new.block_id, new.content);
END;

-- ── Edges table ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_block_id TEXT NOT NULL,
    target_block_id TEXT NOT NULL,
    relation_type   TEXT NOT NULL,
    weight          REAL NOT NULL DEFAULT 0.5,
    is_inferred     BOOLEAN NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_block_id) REFERENCES blocks(block_id) ON DELETE CASCADE,
    FOREIGN KEY (target_block_id) REFERENCES blocks(block_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_block_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_block_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique
    ON edges(source_block_id, target_block_id, relation_type);

-- ── Embeddings metadata (maps block → FAISS index position) ───────────────
CREATE TABLE IF NOT EXISTS embeddings_meta (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id            TEXT NOT NULL,
    faiss_index_position INTEGER NOT NULL,
    model_version       TEXT NOT NULL DEFAULT '',
    is_active           BOOLEAN NOT NULL DEFAULT 1,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (block_id) REFERENCES blocks(block_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emb_block ON embeddings_meta(block_id);
CREATE INDEX IF NOT EXISTS idx_emb_active ON embeddings_meta(is_active);

-- ── Incremental indexing queue ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS index_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path   TEXT NOT NULL,
    queued_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status      TEXT NOT NULL DEFAULT 'pending'  -- pending | processing | done | failed
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON index_queue(status);

-- ── Schema version tracking ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------


class RAGDatabase:
    """Manages the SQLite database for the RAG knowledge graph.

    Thread-safety: each calling thread gets its own SQLite connection via
    threading.local(), so the IndexerDaemon thread and the main/IPC threads
    never share a connection object.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Per-thread connection storage — each thread lazily creates its own conn
        self._local = threading.local()

    def _make_conn(self) -> sqlite3.Connection:
        """Open a new SQLite connection for the calling thread."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the SQLite connection for the current thread, creating it if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._make_conn()
        return self._local.conn

    def initialize(self) -> None:
        """Create tables if they don't exist and track schema version."""
        cursor = self.conn.cursor()

        # Check if already initialized
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if cursor.fetchone():
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] else 0
            if current_version >= _SCHEMA_VERSION:
                return  # Already up to date

        # Create all tables
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (_SCHEMA_VERSION,),
        )
        self.conn.commit()

    def close(self) -> None:
        """Close the calling thread's connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self) -> "RAGDatabase":
        self.initialize()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ── Block CRUD ─────────────────────────────────────────────────────────

    def upsert_block(
        self,
        block_id: str,
        note_id: str,
        note_path: str,
        content: str,
        block_type: str,
        content_hash: str,
    ) -> None:
        """Insert or update a block row."""
        self.conn.execute(
            """
            INSERT INTO blocks (block_id, note_id, note_path, content, block_type, content_hash, last_indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(block_id) DO UPDATE SET
                content      = excluded.content,
                block_type   = excluded.block_type,
                content_hash = excluded.content_hash,
                note_path    = excluded.note_path,
                last_indexed_at = CURRENT_TIMESTAMP
            """,
            (block_id, note_id, note_path, content, block_type, content_hash),
        )
        self.conn.commit()

    def delete_block(self, block_id: str) -> None:
        """Delete a block and cascade to edges + embeddings_meta."""
        self.conn.execute("DELETE FROM blocks WHERE block_id = ?", (block_id,))
        self.conn.commit()

    def get_block(self, block_id: str) -> Optional[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT * FROM blocks WHERE block_id = ?", (block_id,)
        )
        return cursor.fetchone()

    def get_blocks_for_note(self, note_id: str) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT * FROM blocks WHERE note_id = ? ORDER BY rowid", (note_id,)
        )
        return cursor.fetchall()

    def get_all_block_hashes(self, note_id: str) -> dict[str, str]:
        """Return {block_id: content_hash} for all blocks in a note."""
        cursor = self.conn.execute(
            "SELECT block_id, content_hash FROM blocks WHERE note_id = ?", (note_id,)
        )
        return {row["block_id"]: row["content_hash"] for row in cursor.fetchall()}

    # ── Edge CRUD ──────────────────────────────────────────────────────────

    def upsert_edge(
        self,
        source_block_id: str,
        target_block_id: str,
        relation_type: str,
        weight: float,
        is_inferred: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO edges (source_block_id, target_block_id, relation_type, weight, is_inferred)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_block_id, target_block_id, relation_type) DO UPDATE SET
                weight = excluded.weight,
                is_inferred = excluded.is_inferred
            """,
            (source_block_id, target_block_id, relation_type, weight, is_inferred),
        )
        self.conn.commit()

    def delete_edges_for_block(self, block_id: str) -> None:
        """Delete all edges involving a given block."""
        self.conn.execute(
            "DELETE FROM edges WHERE source_block_id = ? OR target_block_id = ?",
            (block_id, block_id),
        )
        self.conn.commit()

    def get_edges(self, block_id: str) -> list[sqlite3.Row]:
        """Get all edges where block_id is source or target."""
        cursor = self.conn.execute(
            "SELECT * FROM edges WHERE source_block_id = ? OR target_block_id = ?",
            (block_id, block_id),
        )
        return cursor.fetchall()

    def get_all_edges(self) -> list[sqlite3.Row]:
        cursor = self.conn.execute("SELECT * FROM edges")
        return cursor.fetchall()

    # ── Embeddings metadata ────────────────────────────────────────────────

    def add_embedding_meta(
        self, block_id: str, faiss_position: int, model_version: str
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO embeddings_meta (block_id, faiss_index_position, model_version)
            VALUES (?, ?, ?)
            """,
            (block_id, faiss_position, model_version),
        )
        self.conn.commit()

    def tombstone_embedding(self, block_id: str) -> None:
        """Mark all embeddings for a block as inactive (tombstoned)."""
        self.conn.execute(
            "UPDATE embeddings_meta SET is_active = 0 WHERE block_id = ?",
            (block_id,),
        )
        self.conn.commit()

    def get_active_embedding(self, block_id: str) -> Optional[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT * FROM embeddings_meta WHERE block_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
            (block_id,),
        )
        return cursor.fetchone()

    def get_active_faiss_positions(self) -> list[int]:
        """Return all active FAISS index positions (for filtering at query time)."""
        cursor = self.conn.execute(
            "SELECT faiss_index_position FROM embeddings_meta WHERE is_active = 1"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_tombstone_ratio(self) -> float:
        """Return the fraction of embeddings that are tombstoned."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as tombstoned FROM embeddings_meta"
        )
        row = cursor.fetchone()
        total = row["total"] if row else 0
        if total == 0:
            return 0.0
        return row["tombstoned"] / total

    def get_block_id_for_faiss_position(self, position: int) -> Optional[str]:
        """Reverse lookup: FAISS position → block_id (active only)."""
        cursor = self.conn.execute(
            "SELECT block_id FROM embeddings_meta WHERE faiss_index_position = ? AND is_active = 1",
            (position,),
        )
        row = cursor.fetchone()
        return row["block_id"] if row else None

    def get_all_active_embeddings(self) -> list[sqlite3.Row]:
        """Get all active embedding records (for compaction rebuild)."""
        cursor = self.conn.execute(
            "SELECT * FROM embeddings_meta WHERE is_active = 1 ORDER BY faiss_index_position"
        )
        return cursor.fetchall()

    def clear_all_embeddings(self) -> None:
        """Delete all embedding records (used during compaction rebuild)."""
        self.conn.execute("DELETE FROM embeddings_meta")
        self.conn.commit()

    # ── Index queue ────────────────────────────────────────────────────────

    def enqueue_note(self, note_path: str) -> None:
        """Add a note to the re-indexing queue if not already pending."""
        self.conn.execute(
            """
            INSERT INTO index_queue (note_path, status)
            SELECT ?, 'pending'
            WHERE NOT EXISTS (
                SELECT 1 FROM index_queue WHERE note_path = ? AND status = 'pending'
            )
            """,
            (note_path, note_path),
        )
        self.conn.commit()

    def dequeue_pending(self, limit: int = 10) -> list[sqlite3.Row]:
        """Fetch and mark pending items as processing."""
        cursor = self.conn.execute(
            "SELECT * FROM index_queue WHERE status = 'pending' ORDER BY queued_at LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        if rows:
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(ids))
            self.conn.execute(
                f"UPDATE index_queue SET status = 'processing' WHERE id IN ({placeholders})",
                ids,
            )
            self.conn.commit()
        return rows

    def mark_queue_done(self, queue_id: int) -> None:
        self.conn.execute(
            "UPDATE index_queue SET status = 'done' WHERE id = ?", (queue_id,)
        )
        self.conn.commit()

    def mark_queue_failed(self, queue_id: int) -> None:
        self.conn.execute(
            "UPDATE index_queue SET status = 'failed' WHERE id = ?", (queue_id,)
        )
        self.conn.commit()

    # ── FTS5 search ────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """
        Strip FTS5 special characters to avoid syntax errors.
        FTS5 treats chars like ?, *, (, ), ", ^ as syntax operators.
        We keep only alphanumeric, whitespace, and hyphens.
        """
        import re

        # Remove FTS5 special characters; collapse whitespace
        cleaned = re.sub(r"[^\w\s\-]", " ", query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or "placeholder"  # never pass empty string to FTS5

    def fts_search(self, query: str, limit: int = 50) -> list[sqlite3.Row]:
        """Full-text search via FTS5. Returns blocks ranked by BM25."""
        safe_query = self._sanitize_fts_query(query)
        try:
            cursor = self.conn.execute(
                """
                SELECT b.*, bm25(blocks_fts) as fts_score
                FROM blocks_fts
                JOIN blocks b ON blocks_fts.block_id = b.block_id
                WHERE blocks_fts MATCH ?
                ORDER BY bm25(blocks_fts)
                LIMIT ?
                """,
                (safe_query, limit),
            )
            return cursor.fetchall()
        except Exception:
            # FTS5 can still raise on edge cases; return empty rather than crash
            return []
