"""
graph.py — NetworkX DiGraph construction and A* traversal for the knowledge graph.

Implements:
  - Graph construction from SQLite edge data
  - A* pathfinding with semantic heuristic h(n) = 1 - cosine_similarity
  - Multi-entry traversal from top-K entry nodes
  - Path merging and deduplication
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np

from .embeddings import EmbeddingManager
from .schema import RAGConfig, RAGDatabase

logger = logging.getLogger(__name__)


@dataclass
class TraversalResult:
    """Result of an A* graph traversal."""

    paths: list[list[str]]  # List of block_id paths
    visited_nodes: set[str] = field(default_factory=set)  # All unique block_ids visited
    node_scores: dict[str, float] = field(
        default_factory=dict
    )  # block_id → relevance to query
    total_cost: float = 0.0


class KnowledgeGraph:
    """
    In-memory directed graph built from SQLite edge data.
    Provides A* traversal with semantic heuristic.
    """

    def __init__(
        self,
        config: RAGConfig,
        db: RAGDatabase,
        embedding_manager: EmbeddingManager,
    ):
        self.config = config
        self.db = db
        self.emb = embedding_manager
        self.graph = nx.DiGraph()

    def build(self) -> int:
        """
        Build the NetworkX graph from all edges in the database.
        Returns the number of edges added.
        """
        self.graph.clear()
        edges = self.db.get_all_edges()

        for edge in edges:
            self.graph.add_edge(
                edge["source_block_id"],
                edge["target_block_id"],
                weight=edge["weight"],
                relation_type=edge["relation_type"],
            )

        logger.info(
            f"Knowledge graph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )
        return self.graph.number_of_edges()

    def update_edges_for_block(self, block_id: str) -> None:
        """
        Refresh the graph edges involving a specific block.
        Called after incremental re-indexing.
        """
        # Remove all existing edges involving this block
        if block_id in self.graph:
            predecessors = list(self.graph.predecessors(block_id))
            successors = list(self.graph.successors(block_id))
            for pred in predecessors:
                self.graph.remove_edge(pred, block_id)
            for succ in successors:
                self.graph.remove_edge(block_id, succ)

        # Re-add from database
        edges = self.db.get_edges(block_id)
        for edge in edges:
            self.graph.add_edge(
                edge["source_block_id"],
                edge["target_block_id"],
                weight=edge["weight"],
                relation_type=edge["relation_type"],
            )

    def remove_block(self, block_id: str) -> None:
        """Remove a block and all its edges from the graph."""
        if block_id in self.graph:
            self.graph.remove_node(block_id)

    # ── A* Traversal ──────────────────────────────────────────────────────

    def astar_traverse(
        self,
        entry_node_ids: list[str],
        query_embedding: np.ndarray,
        max_nodes: int | None = None,
    ) -> TraversalResult:
        """
        Multi-entry A* traversal from the top-K entry nodes.

        For each entry node, runs A* outward, guided by the heuristic
        h(n) = 1 - cosine_similarity(node_embedding, query_embedding).

        Paths from all entry points are merged and deduplicated.

        Args:
            entry_node_ids:  Block IDs to start traversal from
            query_embedding: The user query's embedding vector (D,)
            max_nodes:       Maximum unique nodes to visit total

        Returns:
            TraversalResult with paths, visited nodes, and scores
        """
        if max_nodes is None:
            max_nodes = self.config.astar_max_nodes

        result = TraversalResult(paths=[], visited_nodes=set(), node_scores={})

        # Cache for node embeddings (avoid repeated FAISS lookups)
        embedding_cache: dict[str, np.ndarray] = {}

        # Normalize query embedding for cosine computation
        q_norm = np.linalg.norm(query_embedding)
        if q_norm > 0:
            query_embedding = query_embedding / q_norm

        for entry_id in entry_node_ids:
            if entry_id not in self.graph:
                continue
            if len(result.visited_nodes) >= max_nodes:
                break

            path = self._astar_from_node(
                start_id=entry_id,
                query_embedding=query_embedding,
                embedding_cache=embedding_cache,
                max_nodes=max_nodes - len(result.visited_nodes),
                already_visited=result.visited_nodes,
            )

            if path:
                result.paths.append(path)
                result.visited_nodes.update(path)

        # Compute relevance scores for all visited nodes
        for node_id in result.visited_nodes:
            vec = self._get_node_embedding(node_id, embedding_cache)
            if vec is not None:
                score = float(np.dot(query_embedding, vec))
                result.node_scores[node_id] = score

        return result

    def _astar_from_node(
        self,
        start_id: str,
        query_embedding: np.ndarray,
        embedding_cache: dict[str, np.ndarray],
        max_nodes: int,
        already_visited: set[str],
    ) -> list[str]:
        """
        A* search from a single start node, expanding outward through
        the graph toward the most query-relevant nodes.

        Uses NetworkX's built-in A* with our custom heuristic.
        Returns the path of block IDs traversed.
        """
        # We don't have a single "goal" node — we want to explore relevantly.
        # Strategy: use A* to find paths to the most relevant reachable nodes.
        # We'll collect all reachable nodes scored by f(n) = g(n) + h(n).

        def heuristic(node_id: str, _target: str) -> float:
            """h(n) = 1 - cosine_similarity(node, query). Range [0, 1]."""
            vec = self._get_node_embedding(node_id, embedding_cache)
            if vec is None:
                return 1.0  # Maximum cost for unknown nodes
            sim = float(np.dot(query_embedding, vec))
            return max(0.0, 1.0 - sim)  # Clamp to [0, 1]

        # Explore outward using a priority queue (manual A* for exploration)
        import heapq

        open_set: list[tuple[float, str, list[str]]] = []  # (f_score, node_id, path)
        closed_set: set[str] = set()

        h_start = heuristic(start_id, "")
        heapq.heappush(open_set, (h_start, start_id, [start_id]))

        best_path: list[str] = [start_id]
        best_score = h_start
        nodes_explored = 0

        while open_set and nodes_explored < max_nodes:
            f_score, current, path = heapq.heappop(open_set)

            if current in closed_set:
                continue
            closed_set.add(current)
            nodes_explored += 1

            # Track the best (lowest h) path we've found
            h_current = heuristic(current, "")
            if h_current < best_score:
                best_score = h_current
                best_path = path

            # Expand neighbors
            if current in self.graph:
                for neighbor in self.graph.neighbors(current):
                    if neighbor in closed_set or neighbor in already_visited:
                        continue

                    edge_data = self.graph.edges[current, neighbor]
                    g_new = f_score - heuristic(current, "") + edge_data["weight"]
                    h_new = heuristic(neighbor, "")
                    f_new = g_new + h_new

                    heapq.heappush(open_set, (f_new, neighbor, path + [neighbor]))

        return best_path

    def _get_node_embedding(
        self, node_id: str, cache: dict[str, np.ndarray]
    ) -> Optional[np.ndarray]:
        """Get a node's embedding vector, using cache to avoid repeated lookups."""
        if node_id in cache:
            return cache[node_id]

        vec = self.emb.get_block_vector(node_id)
        if vec is not None:
            # L2-normalize for cosine similarity
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            cache[node_id] = vec
        return vec

    # ── Graph stats ────────────────────────────────────────────────────────

    @property
    def num_nodes(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def num_edges(self) -> int:
        return self.graph.number_of_edges()

    def get_neighbors(self, block_id: str) -> list[tuple[str, str, float]]:
        """Get neighbors of a block: list of (neighbor_id, relation_type, weight)."""
        if block_id not in self.graph:
            return []
        neighbors = []
        for neighbor in self.graph.neighbors(block_id):
            edge_data = self.graph.edges[block_id, neighbor]
            neighbors.append(
                (neighbor, edge_data["relation_type"], edge_data["weight"])
            )
        return neighbors
