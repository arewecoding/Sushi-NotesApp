"""
commands.py — Pipeline orchestrator and IPC-ready command interface.

This is the main entry point that wires together all RAG components
into a single query pipeline. Designed to be called via PyTauri IPC
commands or directly from Python.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .context import AssembledContext, ContextAssembler
from .edges import EdgeInference
from .embeddings import EmbeddingManager
from .graph import KnowledgeGraph, TraversalResult
from .indexer import Indexer, IndexerDaemon
from .llm import LLMClient, LLMResponse
from .reranker import Reranker
from .router import AgenticRouter, RetrievalStrategy
from .schema import HyperParams, RAGConfig, RAGDatabase
from .search import HybridSearch

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Full result from a RAG query pipeline run."""

    answer: str
    strategy: str
    query_original: str
    query_optimized: str
    blocks_retrieved: int
    blocks_reranked: int
    blocks_in_context: int
    context_truncated: bool
    llm_model: str
    llm_usage: dict
    latency: dict = field(default_factory=dict)  # Stage → seconds


class RAGPipeline:
    """
    Orchestrates the full RAG pipeline:
      1. Query Optimizer (LLM rewrites query)
      2. Hybrid Retrieval (SQLite FTS5 + FAISS)
      3. Reranking (API-based)
      4. Agentic Router (Direct Recall vs Graph Traversal)
      5. Context Assembly
      6. LLM Synthesis
    """

    def __init__(
        self, config: RAGConfig, data_dir: Path, hp: HyperParams | None = None
    ):
        self.config = config
        self.data_dir = data_dir
        self.hp = hp or HyperParams()
        data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize all components
        self.db = RAGDatabase(data_dir / "rag.db")
        self.db.initialize()

        self.embedding_manager = EmbeddingManager(config, self.db, data_dir)
        self.edge_inference = EdgeInference(config, self.db, self.hp)
        self.search = HybridSearch(self.db, self.embedding_manager, self.hp)
        self.reranker = Reranker(config, self.hp)
        self.router = AgenticRouter(config, self.hp)
        self.graph = KnowledgeGraph(config, self.db, self.embedding_manager)
        self.context_assembler = ContextAssembler(config, self.db, self.hp)
        self.llm = LLMClient(config, self.hp)
        self.indexer = Indexer(
            config, self.db, self.embedding_manager, self.edge_inference, self.hp
        )
        self.daemon: IndexerDaemon | None = None

    def query(self, query: str) -> PipelineResult:
        """
        Run the full RAG pipeline for a user query.

        This is the main entry point — wire this up to a PyTauri @command.
        """
        latency: dict[str, float] = {}

        # ── Stage 1: Route and optimize the query ────────────────────────
        t0 = time.time()
        routing = self.router.route(query)
        latency["routing"] = time.time() - t0

        optimized_query = routing.optimized_query
        logger.info(
            f"Route: {routing.strategy.value} | "
            f"Original: '{query}' | Optimized: '{optimized_query}'"
        )

        # ── Stage 2: Hybrid retrieval ────────────────────────────────────
        t0 = time.time()
        candidates = self.search.search(
            optimized_query, top_k=self.config.retrieval_top_k
        )
        latency["retrieval"] = time.time() - t0

        if not candidates:
            return PipelineResult(
                answer="No relevant notes found for your query.",
                strategy=routing.strategy.value,
                query_original=query,
                query_optimized=optimized_query,
                blocks_retrieved=0,
                blocks_reranked=0,
                blocks_in_context=0,
                context_truncated=False,
                llm_model=self.config.llm_model,
                llm_usage={},
                latency=latency,
            )

        # ── Stage 3: Reranking ───────────────────────────────────────────
        t0 = time.time()
        reranked = self.reranker.rerank(
            optimized_query, candidates, top_k=self.config.reranker_top_k
        )
        latency["reranking"] = time.time() - t0

        # ── Stage 4: Strategy execution ──────────────────────────────────
        t0 = time.time()
        context: AssembledContext

        if routing.strategy == RetrievalStrategy.CONTEXTUAL_TRAVERSAL:
            # A* traversal from top reranked blocks
            entry_ids = [
                r.block_id for r in reranked[: self.hp.traversal_entry_nodes_count]
            ]
            query_embedding = self.embedding_manager.client.embed_single(
                optimized_query
            )
            traversal = self.graph.astar_traverse(entry_ids, query_embedding)
            latency["traversal"] = time.time() - t0

            t0 = time.time()
            context = self.context_assembler.assemble_from_traversal(
                traversal, optimized_query
            )
        else:
            # Direct recall — assemble from reranked results
            latency["traversal"] = 0.0
            t0 = time.time()
            context = self.context_assembler.assemble_from_rerank(
                reranked, optimized_query
            )

        latency["assembly"] = time.time() - t0

        # ── Stage 5: LLM Synthesis ───────────────────────────────────────
        t0 = time.time()
        llm_response = self.llm.synthesize(context)
        latency["llm"] = time.time() - t0

        latency["total"] = sum(latency.values())

        return PipelineResult(
            answer=llm_response.answer,
            strategy=routing.strategy.value,
            query_original=query,
            query_optimized=optimized_query,
            blocks_retrieved=len(candidates),
            blocks_reranked=len(reranked),
            blocks_in_context=len(context.block_ids),
            context_truncated=context.truncated,
            llm_model=llm_response.model,
            llm_usage=llm_response.usage,
            latency=latency,
        )

    # ── Index management commands ──────────────────────────────────────────

    def build_index(self, notes_dir: Path) -> dict[str, Any]:
        """Full index rebuild. Scans all .jnote files in the directory."""
        stats = self.indexer.build_full_index(notes_dir)
        self.graph.build()
        return {
            "status": "ok",
            **stats,
            "graph_nodes": self.graph.num_nodes,
            "graph_edges": self.graph.num_edges,
        }

    def incremental_index(self, file_path: Path) -> dict[str, Any]:
        """Incrementally update the index for a single note."""
        stats = self.indexer.incremental_update(file_path)
        # Update graph edges for affected blocks
        for block_id in stats.get("affected_block_ids", []):
            self.graph.update_edges_for_block(block_id)
        return {"status": "ok", **stats}

    def status(self) -> dict[str, Any]:
        """Return index health status."""
        return {
            "status": "ok",
            "faiss_vectors": self.embedding_manager.faiss_index.total_vectors,
            "tombstone_ratio": self.db.get_tombstone_ratio(),
            "graph_nodes": self.graph.num_nodes,
            "graph_edges": self.graph.num_edges,
        }

    def start_daemon(self) -> None:
        """Start the background indexer daemon."""
        if self.daemon is None:
            self.daemon = IndexerDaemon(self.indexer, self.config, self.db, self.hp)
        self.daemon.start()

    def stop_daemon(self) -> None:
        """Stop the background indexer daemon."""
        if self.daemon:
            self.daemon.stop()

    def on_note_saved(self, note_path: str) -> None:
        """Notify the daemon that a note was saved (called by watchdog)."""
        if self.daemon:
            self.daemon.on_note_saved(note_path)
        else:
            # No daemon running — do synchronous incremental update
            self.indexer.incremental_update(Path(note_path))

    def shutdown(self) -> None:
        """Clean shutdown: stop daemon, save index, close DB."""
        self.stop_daemon()
        self.embedding_manager.save()
        self.db.close()


# ── Convenience factory ────────────────────────────────────────────────────


def create_pipeline(
    config_path: Path | None = None,
    data_dir: Path | None = None,
    hyperparams_path: Path | None = None,
) -> RAGPipeline:
    """
    Create a fully initialized RAG pipeline.

    Args:
        config_path:      Path to rag_config.json (defaults to cwd)
        data_dir:         Directory to store index data (defaults to cwd/.rag_data)
        hyperparams_path: Path to rag_hyperparams.json (defaults to cwd)
    """
    if config_path is None:
        config_path = Path("rag_config.json")
    if data_dir is None:
        data_dir = Path(".rag_data")
    if hyperparams_path is None:
        hyperparams_path = Path("rag_hyperparams.json")

    config = RAGConfig.load(config_path)
    hp = HyperParams.load(hyperparams_path)
    return RAGPipeline(config, data_dir, hp)
