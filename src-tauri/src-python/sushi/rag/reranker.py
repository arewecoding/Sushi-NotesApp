"""
reranker.py — API-based reranking of candidate blocks.

Uses Google Gemini as an LLM-judge to score relevance of candidate blocks.
"""

import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from .schema import HyperParams, RAGConfig
from .search import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """A reranked search result with the reranker's relevance score."""

    block_id: str
    content: str
    note_id: str
    note_path: str
    block_type: str
    rerank_score: float
    original_rrf_score: float


class Reranker:
    """Reranks candidate blocks using Google Gemini as an LLM-judge."""

    def __init__(self, config: RAGConfig, hp: HyperParams | None = None):
        self.config = config
        self.hp = hp or HyperParams()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.config.google_api_key)
        return self._client

    def rerank(
        self, query: str, candidates: list[SearchResult], top_k: int | None = None
    ) -> list[RerankResult]:
        """
        Rerank candidates and return the top-K most relevant.

        Args:
            query:      The user's search query
            candidates: Candidate blocks from hybrid search
            top_k:      Number of results to return (default from config)

        Returns:
            Reranked results sorted by relevance score (descending)
        """
        if top_k is None:
            top_k = self.config.reranker_top_k

        if not candidates:
            return []

        results = self._rerank_gemini(query, candidates)

        # Sort by score descending, take top-K
        results.sort(key=lambda r: r.rerank_score, reverse=True)
        return results[:top_k]

    def _rerank_gemini(
        self, query: str, candidates: list[SearchResult]
    ) -> list[RerankResult]:
        """
        Rerank using Google Gemini as a judge — send (query, document) pairs
        and ask the LLM to score relevance on a 0-10 scale.
        """
        # Build the scoring prompt
        documents = []
        for i, c in enumerate(candidates):
            content_preview = (
                c.content[: self.hp.reranker_content_preview_max_chars]
                if len(c.content) > self.hp.reranker_content_preview_max_chars
                else c.content
            )
            documents.append(f"[{i}] {content_preview}")

        documents_text = "\n\n".join(documents)

        prompt = f"""You are a relevance scoring engine. Given a query and a list of document passages, 
score each passage's relevance to the query on a scale of 0 to 10.

Query: "{query}"

Documents:
{documents_text}

Return ONLY a JSON array of objects with "index" and "score" keys, like:
[{{"index": 0, "score": 8}}, {{"index": 1, "score": 3}}, ...]

Score each document. Be strict — only high relevance deserves 7+."""

        try:
            response = self.client.models.generate_content(
                model=self.config.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.hp.reranker_temperature,
                    response_mime_type="application/json",
                ),
            )

            content = response.text or "[]"
            scores_data = json.loads(content)

            # Handle both {"results": [...]} and [...] formats
            if isinstance(scores_data, dict):
                scores_list = scores_data.get("results", scores_data.get("scores", []))
            elif isinstance(scores_data, list):
                scores_list = scores_data
            else:
                scores_list = []

            # Map scores back to candidates
            score_map = {}
            for item in scores_list:
                if isinstance(item, dict) and "index" in item and "score" in item:
                    score_map[item["index"]] = (
                        item["score"] / 10.0
                    )  # Normalize to [0,1]

        except Exception as e:
            logger.warning(
                f"Gemini reranking failed: {e}. Using RRF scores as fallback."
            )
            score_map = {i: c.rrf_score for i, c in enumerate(candidates)}

        results = []
        for i, candidate in enumerate(candidates):
            results.append(
                RerankResult(
                    block_id=candidate.block_id,
                    content=candidate.content,
                    note_id=candidate.note_id,
                    note_path=candidate.note_path,
                    block_type=candidate.block_type,
                    rerank_score=score_map.get(i, 0.0),
                    original_rrf_score=candidate.rrf_score,
                )
            )

        return results
