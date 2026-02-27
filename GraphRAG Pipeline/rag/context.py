"""
context.py — Context assembly for the LLM.

Takes traversal results (ordered block paths) and assembles them into a
coherent text prompt with relationship labels, logical ordering, and
token budget management.
"""

import logging
from dataclasses import dataclass

from .graph import TraversalResult
from .reranker import RerankResult
from .schema import HyperParams, RAGConfig, RAGDatabase

logger = logging.getLogger(__name__)


@dataclass
class AssembledContext:
    """The assembled context ready for LLM consumption."""

    context_text: str  # The stitched text
    block_ids: list[str]  # Block IDs included, in order
    total_tokens_est: int  # Estimated token count
    truncated: bool  # Whether truncation was needed
    metadata: dict  # Additional info about the assembly


class ContextAssembler:
    """
    Assembles retrieved/traversed blocks into a coherent context
    for the LLM, respecting token budgets.
    """

    def __init__(
        self, config: RAGConfig, db: RAGDatabase, hp: HyperParams | None = None
    ):
        self.config = config
        self.db = db
        self.hp = hp or HyperParams()

    def assemble_from_traversal(
        self, traversal: TraversalResult, query: str
    ) -> AssembledContext:
        """
        Assemble context from A* traversal results.
        Orders blocks along their paths, adds relationship connectors.
        """
        max_tokens = self.config.context_max_tokens
        max_chars = max_tokens * self.hp.chars_per_token

        sections: list[str] = []
        included_ids: list[str] = []
        total_chars = 0
        truncated = False

        # Sort nodes by relevance score (most relevant first)
        sorted_nodes = sorted(
            traversal.node_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        for block_id, relevance in sorted_nodes:
            block = self.db.get_block(block_id)
            if block is None:
                continue

            content = block["content"]
            block_type = block["block_type"]

            # Format block with metadata
            section = self._format_block(
                block_id=block_id,
                content=content,
                block_type=block_type,
                note_path=block["note_path"],
                relevance=relevance,
            )

            section_chars = len(section)
            if total_chars + section_chars > max_chars:
                truncated = True
                # Try to fit a truncated version
                remaining = max_chars - total_chars
                if remaining > self.hp.min_remaining_chars_for_truncated_block:
                    section = section[:remaining] + "\n[...truncated]"
                    sections.append(section)
                    included_ids.append(block_id)
                break

            sections.append(section)
            included_ids.append(block_id)
            total_chars += section_chars

        context_text = self._build_prompt(query, sections)

        return AssembledContext(
            context_text=context_text,
            block_ids=included_ids,
            total_tokens_est=len(context_text) // self.hp.chars_per_token,
            truncated=truncated,
            metadata={
                "strategy": "contextual_traversal",
                "paths_count": len(traversal.paths),
                "total_nodes_visited": len(traversal.visited_nodes),
                "nodes_included": len(included_ids),
            },
        )

    def assemble_from_rerank(
        self, results: list[RerankResult], query: str
    ) -> AssembledContext:
        """
        Assemble context from directly reranked results (for Direct Recall).
        Simple ordering by rerank score.
        """
        max_tokens = self.config.context_max_tokens
        max_chars = max_tokens * self.hp.chars_per_token

        sections: list[str] = []
        included_ids: list[str] = []
        total_chars = 0
        truncated = False

        for result in results:
            section = self._format_block(
                block_id=result.block_id,
                content=result.content,
                block_type=result.block_type,
                note_path=result.note_path,
                relevance=result.rerank_score,
            )

            section_chars = len(section)
            if total_chars + section_chars > max_chars:
                truncated = True
                remaining = max_chars - total_chars
                if remaining > self.hp.min_remaining_chars_for_truncated_block:
                    section = section[:remaining] + "\n[...truncated]"
                    sections.append(section)
                    included_ids.append(result.block_id)
                break

            sections.append(section)
            included_ids.append(result.block_id)
            total_chars += section_chars

        context_text = self._build_prompt(query, sections)

        return AssembledContext(
            context_text=context_text,
            block_ids=included_ids,
            total_tokens_est=len(context_text) // self.hp.chars_per_token,
            truncated=truncated,
            metadata={
                "strategy": "direct_recall",
                "nodes_included": len(included_ids),
            },
        )

    def _format_block(
        self,
        block_id: str,
        content: str,
        block_type: str,
        note_path: str,
        relevance: float,
    ) -> str:
        """Format a single block for inclusion in the context."""
        # Extract note name from path
        note_name = note_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        note_name = note_name.replace(".jnote", "")

        header = f"--- [{note_name}] (relevance: {relevance:.2f}) ---"

        if block_type == "code":
            body = f"```\n{content}\n```"
        else:
            body = content

        return f"{header}\n{body}\n"

    def _build_prompt(self, query: str, sections: list[str]) -> str:
        """Build the full prompt with system context and assembled blocks."""
        context_body = "\n".join(sections)

        return f"""The following are relevant excerpts from the user's personal notes, 
ordered by relevance to their query. Use these to answer the query accurately.
If the notes don't contain enough information to fully answer, say so.

=== RETRIEVED NOTES ===
{context_body}
=== END NOTES ===

User Query: {query}"""
