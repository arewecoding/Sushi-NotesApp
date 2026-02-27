"""
embeddings.py — Google AI (Gemini) embedding pipeline and FAISS index management.

Handles:
  - Generating embeddings via Google Gemini API (gemini-embedding-001)
  - Managing the FAISS flat index (add, search, save, load)
  - Batch processing .jnote files into embeddings
"""

import logging
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from google import genai

from .schema import HyperParams, RAGConfig, RAGDatabase

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Generates embeddings via Google Gemini API."""

    def __init__(self, config: RAGConfig):
        self.config = config
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.config.google_api_key)
        return self._client

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """
        Embed a batch of texts via the Google Gemini API.
        Returns an (N, D) numpy array of float32 vectors.
        """
        if not texts:
            return np.empty((0, self.config.embedding_dimensions), dtype=np.float32)

        # Google Gemini supports batch embedding via embed_content
        response = self.client.models.embed_content(
            model=self.config.embedding_model,
            contents=texts,
        )

        vectors = [emb.values for emb in response.embeddings]
        return np.array(vectors, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text. Returns a (D,) vector."""
        result = self.embed_texts([text])
        return result[0]


class FAISSIndex:
    """
    Manages a FAISS flat index (IndexFlatIP — inner product, which equals
    cosine similarity when vectors are L2-normalized).

    The index is append-only. Deletions are handled via tombstoning in SQLite,
    with periodic compaction to rebuild the index.
    """

    def __init__(
        self,
        dimensions: int,
        index_path: Optional[Path] = None,
        hp: HyperParams | None = None,
    ):
        self.dimensions = dimensions
        self.index_path = index_path
        self.hp = hp or HyperParams()
        self._index: Optional[faiss.IndexFlatIP] = None

    @property
    def index(self) -> faiss.IndexFlatIP:
        if self._index is None:
            if self.index_path and self.index_path.exists():
                self._index = faiss.read_index(str(self.index_path))
                logger.info(f"Loaded FAISS index with {self._index.ntotal} vectors")
            else:
                self._index = faiss.IndexFlatIP(self.dimensions)
                logger.info(f"Created new FAISS index (dim={self.dimensions})")
        return self._index

    @property
    def total_vectors(self) -> int:
        return self.index.ntotal

    def add_vectors(self, vectors: np.ndarray) -> int:
        """
        Add vectors to the index. Returns the starting position of the
        newly added vectors (i.e., the FAISS position of the first one).
        """
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)

        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)

        start_pos = self.index.ntotal
        self.index.add(vectors)
        return start_pos

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 50,
        active_positions: Optional[set[int]] = None,
    ) -> list[tuple[int, float]]:
        """
        Search the index for the k nearest neighbors.

        Args:
            query_vector: (D,) query embedding
            k:            number of results to return
            active_positions: if provided, only return results at these
                              FAISS positions (filters out tombstoned vectors)

        Returns:
            List of (faiss_position, similarity_score) tuples, sorted by
            descending similarity.
        """
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        faiss.normalize_L2(query_vector)

        # Fetch more than k if we need to filter, so we still get k results
        fetch_k = (
            k * self.hp.faiss_overfetch_multiplier
            if active_positions is not None
            else k
        )
        fetch_k = min(fetch_k, self.index.ntotal)

        if fetch_k == 0:
            return []

        scores, indices = self.index.search(query_vector, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            if active_positions is not None and idx not in active_positions:
                continue
            results.append((int(idx), float(score)))
            if len(results) >= k:
                break

        return results

    def save(self) -> None:
        """Persist the FAISS index to disk."""
        if self._index is not None and self.index_path is not None:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self.index_path))
            logger.info(f"Saved FAISS index ({self._index.ntotal} vectors)")

    def rebuild_from_vectors(self, vectors: np.ndarray) -> None:
        """
        Rebuild the index from scratch with the given vectors.
        Used during compaction to eliminate tombstoned entries.
        """
        self._index = faiss.IndexFlatIP(self.dimensions)
        if vectors.size > 0:
            faiss.normalize_L2(vectors)
            self._index.add(vectors)
        logger.info(f"Rebuilt FAISS index with {self._index.ntotal} vectors")


class EmbeddingManager:
    """
    High-level manager that ties together the embedding client, FAISS index,
    and the database metadata. This is the main interface used by indexer.py.
    """

    def __init__(
        self,
        config: RAGConfig,
        db: RAGDatabase,
        data_dir: Path,
        hp: HyperParams | None = None,
    ):
        self.config = config
        self.db = db
        self.client = EmbeddingClient(config)
        self.faiss_index = FAISSIndex(
            dimensions=config.embedding_dimensions,
            index_path=data_dir / "faiss.index",
            hp=hp,
        )

    def embed_and_store(self, block_id: str, content: str) -> int:
        """
        Embed a block's content and store it in FAISS + metadata.
        Returns the FAISS index position.
        """
        vector = self.client.embed_single(content)
        position = self.faiss_index.add_vectors(vector)
        self.db.add_embedding_meta(
            block_id=block_id,
            faiss_position=position,
            model_version=self.config.embedding_model,
        )
        return position

    def embed_and_store_batch(
        self, block_ids: list[str], contents: list[str]
    ) -> list[int]:
        """
        Embed multiple blocks at once (single API call) and store.
        Returns list of FAISS positions.
        """
        if not block_ids:
            return []

        vectors = self.client.embed_texts(contents)
        start_pos = self.faiss_index.add_vectors(vectors)

        positions = []
        for i, block_id in enumerate(block_ids):
            pos = start_pos + i
            self.db.add_embedding_meta(
                block_id=block_id,
                faiss_position=pos,
                model_version=self.config.embedding_model,
            )
            positions.append(pos)

        return positions

    def tombstone_block(self, block_id: str) -> None:
        """Mark a block's embedding as inactive (tombstoned)."""
        self.db.tombstone_embedding(block_id)

    def search(self, query: str, k: int = 50) -> list[tuple[str, float]]:
        """
        Semantic search: embed the query, search FAISS, filter tombstoned,
        resolve block IDs.

        Returns list of (block_id, similarity_score).
        """
        query_vector = self.client.embed_single(query)

        # Get active positions to filter out tombstoned entries
        active_positions = set(self.db.get_active_faiss_positions())

        results = self.faiss_index.search(
            query_vector, k=k, active_positions=active_positions
        )

        resolved = []
        for position, score in results:
            block_id = self.db.get_block_id_for_faiss_position(position)
            if block_id:
                resolved.append((block_id, score))

        return resolved

    def get_block_vector(self, block_id: str) -> Optional[np.ndarray]:
        """Retrieve the active embedding vector for a block."""
        meta = self.db.get_active_embedding(block_id)
        if meta is None:
            return None
        position = meta["faiss_index_position"]
        vector = self.faiss_index.index.reconstruct(position)
        return vector

    def should_compact(self) -> bool:
        """Check if tombstone ratio exceeds the compaction threshold."""
        return self.db.get_tombstone_ratio() > self.config.tombstone_compaction_ratio

    def compact(self) -> None:
        """
        Rebuild the FAISS index, removing tombstoned entries.
        This re-maps all FAISS positions in the metadata.
        """
        logger.info("Starting FAISS compaction...")
        active_records = self.db.get_all_active_embeddings()

        if not active_records:
            self.faiss_index.rebuild_from_vectors(
                np.empty((0, self.config.embedding_dimensions), dtype=np.float32)
            )
            self.db.clear_all_embeddings()
            self.faiss_index.save()
            return

        # Reconstruct all active vectors
        vectors = []
        block_ids = []
        for record in active_records:
            vec = self.faiss_index.index.reconstruct(record["faiss_index_position"])
            vectors.append(vec)
            block_ids.append(record["block_id"])

        vectors_np = np.array(vectors, dtype=np.float32)

        # Rebuild the FAISS index
        self.faiss_index.rebuild_from_vectors(vectors_np)

        # Clear and re-create metadata with new positions
        self.db.clear_all_embeddings()
        for i, block_id in enumerate(block_ids):
            self.db.add_embedding_meta(
                block_id=block_id,
                faiss_position=i,
                model_version=self.config.embedding_model,
            )

        self.faiss_index.save()
        logger.info(f"Compaction complete. {len(block_ids)} active vectors remain.")

    def save(self) -> None:
        """Persist the FAISS index to disk."""
        self.faiss_index.save()
