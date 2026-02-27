"""
edges.py — Edge inference for the knowledge graph.

Creates edges between blocks from two sources:
  1. Explicit: User-defined backlinks and shared tags in .jnote files
  2. Auto-inferred: Semantic similarity above a threshold
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from .schema import HyperParams, RAGConfig, RAGDatabase

logger = logging.getLogger(__name__)


def parse_jnote(file_path: Path) -> dict[str, Any]:
    """Parse a .jnote file and return its JSON content."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_blocks_from_jnote(jnote_data: dict, note_path: str) -> list[dict[str, Any]]:
    """
    Extract block records from parsed .jnote data.

    Returns a list of dicts with keys:
      block_id, note_id, note_path, content, block_type, tags, backlinks
    """
    note_id = jnote_data.get("metadata", {}).get("note_id", "")
    blocks_data = jnote_data.get("blocks", [])

    blocks = []
    for block in blocks_data:
        block_id = block.get("block_id", "")
        block_type = block.get("type", "text")
        data = block.get("data", {})

        # Content extraction: use 'content' for text, 'code' for code blocks
        content = data.get("content", "")
        if block_type == "code":
            content = data.get("code", content)

        # Skip empty blocks
        if not content.strip():
            continue

        blocks.append(
            {
                "block_id": block_id,
                "note_id": note_id,
                "note_path": note_path,
                "content": content,
                "block_type": block_type,
                "tags": block.get("tags", []),
                "backlinks": block.get("backlinks", []),
            }
        )

    return blocks


class EdgeInference:
    """Infers and manages edges between blocks in the knowledge graph."""

    def __init__(
        self, config: RAGConfig, db: RAGDatabase, hp: HyperParams | None = None
    ):
        self.config = config
        self.db = db
        self.hp = hp or HyperParams()

    def infer_edges_for_note(self, note_path: str) -> int:
        """
        Infer all explicit edges from a single .jnote file.
        Returns the number of edges created.
        """
        jnote_data = parse_jnote(Path(note_path))
        blocks = extract_blocks_from_jnote(jnote_data, note_path)
        edge_count = 0

        block_ids_in_note = [b["block_id"] for b in blocks]

        for block in blocks:
            # ── Same-note edges (sequential blocks are related) ──────────
            for other_id in block_ids_in_note:
                if other_id != block["block_id"]:
                    self.db.upsert_edge(
                        source_block_id=block["block_id"],
                        target_block_id=other_id,
                        relation_type="same_note",
                        weight=self.hp.edge_weights["same_note"],
                        is_inferred=True,
                    )
                    edge_count += 1

            # ── Backlink edges ───────────────────────────────────────────
            for backlink_id in block.get("backlinks", []):
                # Backlinks reference other block IDs
                target_exists = self.db.get_block(backlink_id)
                if target_exists:
                    self.db.upsert_edge(
                        source_block_id=block["block_id"],
                        target_block_id=backlink_id,
                        relation_type="backlink",
                        weight=self.hp.edge_weights["backlink"],
                        is_inferred=False,
                    )
                    # Backlinks are bidirectional
                    self.db.upsert_edge(
                        source_block_id=backlink_id,
                        target_block_id=block["block_id"],
                        relation_type="backlink",
                        weight=self.hp.edge_weights["backlink"],
                        is_inferred=False,
                    )
                    edge_count += 2

        # ── Shared-tag edges (between blocks in any note) ────────────────
        edge_count += self._infer_shared_tag_edges(blocks)

        return edge_count

    def _infer_shared_tag_edges(self, blocks: list[dict]) -> int:
        """
        Create edges between blocks that share tags.
        Checks both blocks within this note AND blocks in the global DB.
        """
        edge_count = 0
        for block in blocks:
            tags = block.get("tags", [])
            if not tags:
                continue

            # Find all other blocks in the DB that share any of these tags
            # For now, we check blocks within the same note first
            # (cross-note tag matching happens during full reindex)
            for other_block in blocks:
                if other_block["block_id"] == block["block_id"]:
                    continue
                other_tags = other_block.get("tags", [])
                shared = set(tags) & set(other_tags)
                if shared:
                    self.db.upsert_edge(
                        source_block_id=block["block_id"],
                        target_block_id=other_block["block_id"],
                        relation_type="shared_tag",
                        weight=self.hp.edge_weights["shared_tag"],
                        is_inferred=True,
                    )
                    edge_count += 1

        return edge_count

    def infer_semantic_edges(
        self,
        block_id: str,
        block_vector: np.ndarray,
        all_block_ids: list[str],
        all_vectors: np.ndarray,
        threshold: float | None = None,
    ) -> int:
        """
        Create edges between a block and other blocks whose semantic
        similarity exceeds the threshold.

        Args:
            block_id:       The block to find neighbors for
            block_vector:   Its embedding vector (D,)
            all_block_ids:  IDs of candidate blocks to compare against
            all_vectors:    Embedding matrix (N, D) of candidate blocks
            threshold:      Cosine similarity threshold (default from config)

        Returns:
            Number of semantic edges created.
        """
        if threshold is None:
            threshold = self.config.similarity_threshold

        if all_vectors.size == 0:
            return 0

        # Compute cosine similarities
        # Vectors should already be L2-normalized from FAISS
        block_vec_norm = block_vector / (np.linalg.norm(block_vector) + 1e-10)
        norms = np.linalg.norm(all_vectors, axis=1, keepdims=True) + 1e-10
        all_vecs_norm = all_vectors / norms
        similarities = all_vecs_norm @ block_vec_norm

        edge_count = 0
        for i, (other_id, sim) in enumerate(zip(all_block_ids, similarities)):
            if other_id == block_id:
                continue
            if sim >= threshold:
                self.db.upsert_edge(
                    source_block_id=block_id,
                    target_block_id=other_id,
                    relation_type="semantically_similar",
                    weight=self.hp.edge_weights["semantically_similar"],
                    is_inferred=True,
                )
                self.db.upsert_edge(
                    source_block_id=other_id,
                    target_block_id=block_id,
                    relation_type="semantically_similar",
                    weight=self.hp.edge_weights["semantically_similar"],
                    is_inferred=True,
                )
                edge_count += 2

        return edge_count

    def clear_edges_for_block(self, block_id: str) -> None:
        """Remove all edges involving a block (for re-inference after edit)."""
        self.db.delete_edges_for_block(block_id)
