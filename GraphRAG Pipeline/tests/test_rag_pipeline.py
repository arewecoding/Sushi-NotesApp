"""
test_rag_pipeline.py — Unit tests for individual RAG components.

Tests the data layer, embeddings, search, edge inference, and A* traversal
using mocked API calls where needed.
"""

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_config():
    """Create a test config."""
    from rag.schema import RAGConfig

    return RAGConfig(
        embedding_dimensions=8,  # Small for testing
        embedding_model="test-model",
        google_api_key="test-key",
        similarity_threshold=0.8,
    )


@pytest.fixture
def test_db(temp_dir):
    """Create an initialized test database."""
    from rag.schema import RAGDatabase

    db = RAGDatabase(temp_dir / "test.db")
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def sample_jnote(temp_dir):
    """Create a sample .jnote file for testing."""
    note = {
        "metadata": {
            "note_id": "test-note-001",
            "title": "Test Note",
            "created_at": "2026-01-01T00:00:00Z",
            "last_modified": "2026-01-01T00:00:00Z",
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": "",
        },
        "custom_fields": {},
        "blocks": [
            {
                "block_id": "block-aaa",
                "type": "text",
                "data": {
                    "content": "Machine learning is a subset of artificial intelligence.",
                    "format": "markdown",
                },
                "version": "1.0",
                "tags": ["ai", "ml"],
                "backlinks": [],
            },
            {
                "block_id": "block-bbb",
                "type": "text",
                "data": {
                    "content": "Neural networks are used in deep learning.",
                    "format": "markdown",
                },
                "version": "1.0",
                "tags": ["ai", "dl"],
                "backlinks": [],
            },
            {
                "block_id": "block-ccc",
                "type": "code",
                "data": {
                    "code": "model.fit(X_train, y_train)",
                    "content": "model.fit(X_train, y_train)",
                },
                "version": "1.0",
                "tags": ["ml"],
                "backlinks": [],
            },
        ],
    }
    path = temp_dir / "test-note-001.jnote"
    with open(path, "w") as f:
        json.dump(note, f)
    return path


# ── Schema tests ───────────────────────────────────────────────────────────


class TestRAGDatabase:
    def test_initialize_creates_tables(self, test_db):
        """Verify all tables are created."""
        cursor = test_db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "blocks" in tables
        assert "edges" in tables
        assert "embeddings_meta" in tables
        assert "index_queue" in tables
        assert "schema_version" in tables

    def test_upsert_and_get_block(self, test_db):
        """Test block insertion and retrieval."""
        test_db.upsert_block(
            block_id="b1",
            note_id="n1",
            note_path="/test/note.jnote",
            content="Hello world",
            block_type="text",
            content_hash="abc123",
        )
        block = test_db.get_block("b1")
        assert block is not None
        assert block["content"] == "Hello world"
        assert block["content_hash"] == "abc123"

    def test_upsert_block_updates(self, test_db):
        """Test that upserting an existing block updates it."""
        test_db.upsert_block("b1", "n1", "/path", "old content", "text", "hash1")
        test_db.upsert_block("b1", "n1", "/path", "new content", "text", "hash2")
        block = test_db.get_block("b1")
        assert block["content"] == "new content"
        assert block["content_hash"] == "hash2"

    def test_delete_block(self, test_db):
        """Test block deletion."""
        test_db.upsert_block("b1", "n1", "/path", "content", "text", "hash1")
        test_db.delete_block("b1")
        assert test_db.get_block("b1") is None

    def test_edge_crud(self, test_db):
        """Test edge creation and retrieval."""
        test_db.upsert_block("b1", "n1", "/path", "c1", "text", "h1")
        test_db.upsert_block("b2", "n1", "/path", "c2", "text", "h2")

        test_db.upsert_edge("b1", "b2", "shared_tag", 0.3, is_inferred=True)
        edges = test_db.get_edges("b1")
        assert len(edges) == 1
        assert edges[0]["relation_type"] == "shared_tag"
        assert edges[0]["weight"] == 0.3

    def test_embedding_tombstone(self, test_db):
        """Test embedding tombstoning."""
        # Need a block first for FK constraint
        test_db.upsert_block("b1", "n1", "/path", "content", "text", "h1")
        test_db.add_embedding_meta("b1", faiss_position=0, model_version="test")
        test_db.tombstone_embedding("b1")

        active = test_db.get_active_embedding("b1")
        assert active is None

        ratio = test_db.get_tombstone_ratio()
        assert ratio == 1.0

    def test_fts_search(self, test_db):
        """Test FTS5 full-text search."""
        test_db.upsert_block(
            "b1", "n1", "/path", "machine learning algorithms", "text", "h1"
        )
        test_db.upsert_block(
            "b2", "n1", "/path", "cooking recipes for dinner", "text", "h2"
        )

        results = test_db.fts_search("machine learning")
        assert len(results) >= 1
        assert results[0]["block_id"] == "b1"

    def test_index_queue(self, test_db):
        """Test index queue operations."""
        test_db.enqueue_note("/path/note.jnote")
        pending = test_db.dequeue_pending(limit=5)
        assert len(pending) == 1
        assert pending[0]["note_path"] == "/path/note.jnote"
        # After dequeue, status becomes 'processing' in DB
        # but the returned row still shows the fetched data

        test_db.mark_queue_done(pending[0]["id"])

    def test_block_hashes(self, test_db):
        """Test getting all block hashes for a note."""
        test_db.upsert_block("b1", "n1", "/path", "c1", "text", "hash_a")
        test_db.upsert_block("b2", "n1", "/path", "c2", "text", "hash_b")
        test_db.upsert_block("b3", "n2", "/path", "c3", "text", "hash_c")

        hashes = test_db.get_all_block_hashes("n1")
        assert hashes == {"b1": "hash_a", "b2": "hash_b"}


# ── Edge inference tests ───────────────────────────────────────────────────


class TestEdgeInference:
    def test_extract_blocks_from_jnote(self, sample_jnote):
        """Test .jnote parsing extracts correct blocks."""
        from rag.edges import extract_blocks_from_jnote, parse_jnote

        data = parse_jnote(sample_jnote)
        blocks = extract_blocks_from_jnote(data, str(sample_jnote))

        assert len(blocks) == 3
        assert blocks[0]["block_id"] == "block-aaa"
        assert (
            blocks[0]["content"]
            == "Machine learning is a subset of artificial intelligence."
        )
        assert blocks[2]["block_type"] == "code"
        assert blocks[2]["content"] == "model.fit(X_train, y_train)"

    def test_shared_tag_edges(self, test_db, sample_config, sample_jnote):
        """Test that shared tags create edges."""
        from rag.edges import EdgeInference

        # First populate the blocks in DB
        test_db.upsert_block(
            "block-aaa", "test-note-001", str(sample_jnote), "ML content", "text", "h1"
        )
        test_db.upsert_block(
            "block-bbb", "test-note-001", str(sample_jnote), "DL content", "text", "h2"
        )
        test_db.upsert_block(
            "block-ccc",
            "test-note-001",
            str(sample_jnote),
            "Code content",
            "code",
            "h3",
        )

        inference = EdgeInference(sample_config, test_db)
        edge_count = inference.infer_edges_for_note(str(sample_jnote))

        # Should create same_note edges + shared_tag edges
        assert edge_count > 0

        # block-aaa (tags: ai, ml) and block-bbb (tags: ai, dl) share "ai"
        # block-aaa (tags: ai, ml) and block-ccc (tags: ml) share "ml"
        edges_aaa = test_db.get_edges("block-aaa")
        relation_types = [e["relation_type"] for e in edges_aaa]
        assert "same_note" in relation_types
        assert "shared_tag" in relation_types

    def test_semantic_edges(self, test_db, sample_config):
        """Test semantic similarity edge inference."""
        from rag.edges import EdgeInference

        test_db.upsert_block("b1", "n1", "/p", "c1", "text", "h1")
        test_db.upsert_block("b2", "n1", "/p", "c2", "text", "h2")

        inference = EdgeInference(sample_config, test_db)

        # Create similar vectors
        vec_a = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        vec_b = np.array([0.95, 0.05, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        vec_c = np.array([0, 0, 0, 0, 0, 0, 0, 1], dtype=np.float32)

        # b1 and b2 are similar, b3 is different
        count = inference.infer_semantic_edges(
            block_id="b1",
            block_vector=vec_a,
            all_block_ids=["b2", "b3"],
            all_vectors=np.vstack([vec_b, vec_c]),
            threshold=0.8,
        )

        # Should create edge between b1 and b2 (similar), not b3
        assert count >= 2  # bidirectional


# ── FAISS index tests ──────────────────────────────────────────────────────


class TestFAISSIndex:
    def test_add_and_search(self, temp_dir):
        """Test FAISS vector addition and search."""
        from rag.embeddings import FAISSIndex

        index = FAISSIndex(dimensions=8, index_path=temp_dir / "test.index")

        # Add some vectors
        vectors = np.random.randn(5, 8).astype(np.float32)
        start = index.add_vectors(vectors)
        assert start == 0
        assert index.total_vectors == 5

        # Search — should find closest match
        query = vectors[2].copy()  # Search for the 3rd vector
        results = index.search(query, k=3)
        assert len(results) == 3
        assert results[0][0] == 2  # Closest should be itself

    def test_save_and_load(self, temp_dir):
        """Test FAISS index persistence."""
        from rag.embeddings import FAISSIndex

        index_path = temp_dir / "test.index"
        index = FAISSIndex(dimensions=8, index_path=index_path)
        vectors = np.random.randn(3, 8).astype(np.float32)
        index.add_vectors(vectors)
        index.save()

        # Load in new instance
        index2 = FAISSIndex(dimensions=8, index_path=index_path)
        assert index2.total_vectors == 3

    def test_active_position_filtering(self, temp_dir):
        """Test that search respects active position filter."""
        from rag.embeddings import FAISSIndex

        index = FAISSIndex(dimensions=8, index_path=temp_dir / "test.index")
        vectors = np.random.randn(5, 8).astype(np.float32)
        index.add_vectors(vectors)

        # Only allow positions 0 and 2
        active = {0, 2}
        results = index.search(vectors[0], k=5, active_positions=active)

        # All returned positions should be in active set
        for pos, score in results:
            assert pos in active

    def test_rebuild(self, temp_dir):
        """Test index rebuild from scratch."""
        from rag.embeddings import FAISSIndex

        index = FAISSIndex(dimensions=8, index_path=temp_dir / "test.index")
        vectors = np.random.randn(10, 8).astype(np.float32)
        index.add_vectors(vectors)
        assert index.total_vectors == 10

        # Rebuild with fewer vectors
        new_vectors = vectors[:5].copy()
        index.rebuild_from_vectors(new_vectors)
        assert index.total_vectors == 5


# ── Hybrid search tests ───────────────────────────────────────────────────


class TestHybridSearch:
    def test_rrf_fusion(self, test_db, sample_config, temp_dir):
        """Test that RRF correctly merges FTS5 and semantic results."""
        from rag.search import HybridSearch, SearchResult

        # We'll test the fusion logic directly
        fts_results = [
            SearchResult(
                block_id="b1",
                content="c1",
                note_id="n1",
                note_path="/p",
                block_type="text",
                fts_rank=1,
                fts_score=5.0,
            ),
            SearchResult(
                block_id="b2",
                content="c2",
                note_id="n1",
                note_path="/p",
                block_type="text",
                fts_rank=2,
                fts_score=3.0,
            ),
        ]
        semantic_results = [
            SearchResult(
                block_id="b2",
                content="c2",
                note_id="n1",
                note_path="/p",
                block_type="text",
                semantic_rank=1,
                semantic_score=0.95,
            ),
            SearchResult(
                block_id="b3",
                content="c3",
                note_id="n1",
                note_path="/p",
                block_type="text",
                semantic_rank=2,
                semantic_score=0.8,
            ),
        ]

        mock_emb = MagicMock()
        search = HybridSearch(test_db, mock_emb)
        merged = search._rrf_fuse(fts_results, semantic_results)

        # b2 appears in both → should have highest RRF score
        scores = {r.block_id: r.rrf_score for r in merged}
        assert scores["b2"] > scores["b1"]  # b2 in both lists
        assert scores["b2"] > scores["b3"]  # b2 in both lists
        assert len(merged) == 3  # b1, b2, b3


# ── Content hash tests ────────────────────────────────────────────────────


class TestContentHash:
    def test_hash_deterministic(self):
        """Same content produces same hash."""
        from rag.indexer import content_hash

        h1 = content_hash("Hello world")
        h2 = content_hash("Hello world")
        assert h1 == h2

    def test_hash_different_content(self):
        """Different content produces different hash."""
        from rag.indexer import content_hash

        h1 = content_hash("Hello world")
        h2 = content_hash("Goodbye world")
        assert h1 != h2


# ── A* traversal tests ────────────────────────────────────────────────────


class TestAStarTraversal:
    def test_astar_finds_path(self, test_db, sample_config, temp_dir):
        """Test A* traversal on a hand-crafted graph."""
        from rag.embeddings import EmbeddingManager, FAISSIndex
        from rag.graph import KnowledgeGraph

        # Create mock embedding manager
        mock_emb = MagicMock(spec=EmbeddingManager)
        mock_emb.faiss_index = FAISSIndex(
            dimensions=8, index_path=temp_dir / "test.index"
        )

        graph = KnowledgeGraph(sample_config, test_db, mock_emb)

        # Build a simple graph: A → B → C
        graph.graph.add_edge("A", "B", weight=0.2, relation_type="shared_tag")
        graph.graph.add_edge("B", "C", weight=0.3, relation_type="shared_tag")
        graph.graph.add_edge("A", "D", weight=0.9, relation_type="semantically_similar")

        # Mock embeddings: B and C are more relevant to query than A; D is far
        query_vec = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)

        def mock_get_vector(node_id):
            vecs = {
                "A": np.array([0.5, 0.5, 0.5, 0, 0, 0, 0, 0], dtype=np.float32),
                "B": np.array([0.95, 0.05, 0, 0, 0, 0, 0, 0], dtype=np.float32),
                "C": np.array([0.98, 0.02, 0, 0, 0, 0, 0, 0], dtype=np.float32),
                "D": np.array([0, 0, 0, 0, 0, 0, 0, 1], dtype=np.float32),
            }
            return vecs.get(node_id)

        mock_emb.get_block_vector = mock_get_vector

        result = graph.astar_traverse(["A"], query_vec, max_nodes=10)

        # Should visit A and expand to B/C (more relevant), avoiding D
        assert "A" in result.visited_nodes
        assert len(result.visited_nodes) >= 2  # Should explore beyond A
        assert len(result.paths) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
