"""
router.py — Agentic router and query optimizer.

Determines the retrieval strategy for each query:
  1. Direct Recall:       Simple factual queries → answer from top reranked blocks
  2. Contextual Traversal: Complex multi-concept queries → A* graph traversal

Uses Google Gemini for query analysis and optimization.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum

from google import genai
from google.genai import types

from .schema import HyperParams, RAGConfig

logger = logging.getLogger(__name__)


class RetrievalStrategy(Enum):
    """The two retrieval strategies the router can choose."""

    DIRECT_RECALL = "direct_recall"
    CONTEXTUAL_TRAVERSAL = "contextual_traversal"


@dataclass
class RoutingDecision:
    """The router's decision on how to handle a query."""

    strategy: RetrievalStrategy
    reasoning: str
    optimized_query: str  # Rewritten query for better retrieval
    sub_queries: list[str]  # Decomposed sub-queries (for complex queries)


class AgenticRouter:
    """
    Classifies user queries and determines the optimal retrieval strategy.
    Uses Google Gemini to analyze query complexity and intent.
    """

    def __init__(self, config: RAGConfig, hp: HyperParams | None = None):
        self.config = config
        self.hp = hp or HyperParams()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.config.google_api_key)
        return self._client

    def route(self, query: str) -> RoutingDecision:
        """
        Analyze the query and decide on the retrieval strategy.

        Direct Recall: "What is X?" / "When did Y happen?" / simple lookups
        Contextual Traversal: "How does X relate to Y?" / "Explain the
                              connection between A and B" / synthesis queries
        """
        prompt = f"""You are a query analysis engine for a personal knowledge management system.
Analyze the user's query and determine the best retrieval strategy.

User Query: "{query}"

You must return a JSON object with these fields:
1. "strategy": either "direct_recall" or "contextual_traversal"
   - "direct_recall": For simple factual queries that can be answered from a single note block 
     or a small set of directly relevant blocks. Examples: "What is X?", 
     "Find my notes about Y", "When did Z happen?"
   - "contextual_traversal": For complex queries that require understanding relationships 
     between multiple concepts, synthesizing information across notes, or tracing logical 
     connections. Examples: "How does X relate to Y?", "What are the implications of X 
     for Y?", "Summarize everything about X and its connections"

2. "reasoning": A brief explanation of why you chose this strategy (1-2 sentences).

3. "optimized_query": A rewritten version of the query that is more descriptive, specific, 
   and better suited for semantic search. Expand abbreviations, add context, and make it 
   more searchable. Keep it concise.

4. "sub_queries": For contextual_traversal, decompose the query into 2-4 sub-queries that 
   each target a specific concept. For direct_recall, this should be an empty array.

Return ONLY the JSON object, no other text."""

        try:
            response = self.client.models.generate_content(
                model=self.config.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.hp.routing_temperature,
                    response_mime_type="application/json",
                ),
            )

            content = response.text or "{}"
            data = json.loads(content)

            strategy_str = data.get("strategy", "direct_recall")
            strategy = (
                RetrievalStrategy.CONTEXTUAL_TRAVERSAL
                if strategy_str == "contextual_traversal"
                else RetrievalStrategy.DIRECT_RECALL
            )

            return RoutingDecision(
                strategy=strategy,
                reasoning=data.get("reasoning", ""),
                optimized_query=data.get("optimized_query", query),
                sub_queries=data.get("sub_queries", []),
            )

        except Exception as e:
            logger.warning(f"Router LLM call failed: {e}. Defaulting to direct recall.")
            return RoutingDecision(
                strategy=RetrievalStrategy.DIRECT_RECALL,
                reasoning=f"LLM routing failed ({e}), defaulting to direct recall.",
                optimized_query=query,
                sub_queries=[],
            )


class QueryOptimizer:
    """
    Standalone query optimizer for use without the full routing decision.
    Rewrites queries to be more effective for semantic search.
    """

    def __init__(self, config: RAGConfig, hp: HyperParams | None = None):
        self.config = config
        self.hp = hp or HyperParams()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.config.google_api_key)
        return self._client

    def optimize(self, query: str) -> str:
        """Rewrite a query to be more descriptive and searchable."""
        prompt = f"""Rewrite this search query to be more descriptive and effective for 
semantic search in a personal notes database. Expand abbreviations, add relevant context, 
and make it more specific. Keep it concise (1-2 sentences max).

Original query: "{query}"

Return ONLY the rewritten query text, nothing else."""

        try:
            response = self.client.models.generate_content(
                model=self.config.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.hp.optimization_temperature
                ),
            )
            return response.text.strip().strip('"')
        except Exception as e:
            logger.warning(f"Query optimization failed: {e}. Using original query.")
            return query
