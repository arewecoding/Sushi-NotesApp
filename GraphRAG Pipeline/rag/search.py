"""
search.py — Hybrid retrieval combining SQLite FTS5 (keyword) and FAISS (semantic).

Uses Reciprocal Rank Fusion (RRF) to merge both result sets into a single
ranked list of candidate blocks.
"""

import logging
from dataclasses import dataclass

from .embeddings import EmbeddingManager
from .schema import HyperParams, RAGDatabase

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with scores from each retrieval source."""

    block_id: str
    content: str
    note_id: str
    note_path: str
    block_type: str
    fts_rank: int | None = None  # Rank in FTS5 results (1-based)
    semantic_rank: int | None = None  # Rank in FAISS results (1-based)
    fts_score: float = 0.0  # Raw BM25 score
    semantic_score: float = 0.0  # Cosine similarity score
    rrf_score: float = 0.0  # Final fused score


class HybridSearch:
    """
    Performs hybrid retrieval: FTS5 (keyword/BM25) + FAISS (semantic),
    merging results via Reciprocal Rank Fusion.
    """

    def __init__(
        self,
        db: RAGDatabase,
        embedding_manager: EmbeddingManager,
        hp: HyperParams | None = None,
    ):
        self.db = db
        self.emb = embedding_manager
        self.hp = hp or HyperParams()

    def search(self, query: str, top_k: int = 50) -> list[SearchResult]:
        """
        Run hybrid search and return the top-k results ranked by RRF score.

        Steps:
          1. FTS5 keyword search  →  ranked list A
          2. FAISS semantic search  →  ranked list B
          3. RRF fusion  →  merged ranked list
        """
        # ── Step 1: FTS5 keyword search ──────────────────────────────────
        fts_results = self._fts_search(
            query, limit=top_k * self.hp.retrieval_overfetch_multiplier
        )

        # ── Step 2: FAISS semantic search ────────────────────────────────
        semantic_results = self._semantic_search(
            query, limit=top_k * self.hp.retrieval_overfetch_multiplier
        )

        # ── Step 3: Reciprocal Rank Fusion ───────────────────────────────
        merged = self._rrf_fuse(fts_results, semantic_results)

        # Sort by RRF score (descending) and return top_k
        merged.sort(key=lambda r: r.rrf_score, reverse=True)
        return merged[:top_k]

    def _fts_search(self, query: str, limit: int) -> list[SearchResult]:
        """Run FTS5 keyword search."""
        try:
            rows = self.db.fts_search(query, limit=limit)
        except Exception as e:
            # FTS5 can fail on weird query syntax — fall back gracefully
            logger.warning(f"FTS5 search failed for query '{query}': {e}")
            return []

        results = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                SearchResult(
                    block_id=row["block_id"],
                    content=row["content"],
                    note_id=row["note_id"],
                    note_path=row["note_path"],
                    block_type=row["block_type"],
                    fts_rank=rank,
                    fts_score=abs(row["fts_score"]),  # BM25 returns negative scores
                )
            )
        return results

    def _semantic_search(self, query: str, limit: int) -> list[SearchResult]:
        """Run FAISS semantic search."""
        semantic_hits = self.emb.search(query, k=limit)

        results = []
        for rank, (block_id, score) in enumerate(semantic_hits, start=1):
            block = self.db.get_block(block_id)
            if block is None:
                continue
            results.append(
                SearchResult(
                    block_id=block_id,
                    content=block["content"],
                    note_id=block["note_id"],
                    note_path=block["note_path"],
                    block_type=block["block_type"],
                    semantic_rank=rank,
                    semantic_score=score,
                )
            )
        return results

    def _rrf_fuse(
        self,
        fts_results: list[SearchResult],
        semantic_results: list[SearchResult],
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion.

        RRF score = Σ  1 / (k + rank_i)

        Where k is a constant (60) and rank_i is the rank in each source.
        This method is robust because it doesn't depend on raw score scales
        — only on the relative ordering.
        """
        results_by_id: dict[str, SearchResult] = {}

        # Add FTS results
        for result in fts_results:
            results_by_id[result.block_id] = result

        # Merge semantic results
        for result in semantic_results:
            if result.block_id in results_by_id:
                # Block appeared in both — merge scores
                existing = results_by_id[result.block_id]
                existing.semantic_rank = result.semantic_rank
                existing.semantic_score = result.semantic_score
            else:
                results_by_id[result.block_id] = result

        # Compute RRF scores
        for result in results_by_id.values():
            rrf = 0.0
            if result.fts_rank is not None:
                rrf += 1.0 / (self.hp.rrf_k + result.fts_rank)
            if result.semantic_rank is not None:
                rrf += 1.0 / (self.hp.rrf_k + result.semantic_rank)
            result.rrf_score = rrf

        return list(results_by_id.values())
