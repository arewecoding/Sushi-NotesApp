"""
evaluation.py — Evaluation and benchmarking harness for the RAG pipeline.

Measures:
  - Component-level metrics (recall, NDCG, path quality, faithfulness)
  - End-to-end pipeline quality against a golden test corpus
  - Per-stage latency (P50/P95)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from google import genai
from google.genai import types

from .commands import RAGPipeline
from .schema import HyperParams, RAGConfig

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class TestCase:
    """A single evaluation test case from the golden corpus."""

    query: str
    expected_block_ids: list[str]  # Ground truth relevant blocks
    expected_key_points: list[str]  # Key points the answer should cover
    strategy_hint: str = ""  # Expected routing strategy
    tags: list[str] = field(default_factory=list)  # e.g., ["single-hop", "factual"]


@dataclass
class TestResult:
    """Result of evaluating a single test case."""

    query: str
    # Retrieval metrics
    recall_at_k: float = 0.0  # How many expected blocks were retrieved
    precision_at_k: float = 0.0  # How many retrieved blocks were relevant
    mrr: float = 0.0  # Mean Reciprocal Rank
    # Reranker metrics
    ndcg_at_10: float = 0.0  # Normalized Discounted Cumulative Gain
    # Router metrics
    routing_correct: bool = False  # Was the strategy correct?
    # LLM answer metrics
    faithfulness: float = 0.0  # Answer claims traceable to context
    answer_relevance: float = 0.0  # How relevant is the answer to query
    coverage: float = 0.0  # Key points covered
    # Latency
    latency: dict = field(default_factory=dict)
    # Details
    answer: str = ""
    strategy_used: str = ""
    blocks_retrieved: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    """Aggregate benchmark results."""

    timestamp: str
    total_cases: int
    # Aggregated metrics (averages)
    avg_recall: float = 0.0
    avg_precision: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg: float = 0.0
    routing_accuracy: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    avg_coverage: float = 0.0
    # Latency stats
    latency_p50: dict = field(default_factory=dict)
    latency_p95: dict = field(default_factory=dict)
    # Individual results
    results: list[TestResult] = field(default_factory=list)


# ── Evaluation engine ──────────────────────────────────────────────────────


class Evaluator:
    """Runs evaluation against a golden test corpus."""

    def __init__(
        self, pipeline: RAGPipeline, config: RAGConfig, hp: HyperParams | None = None
    ):
        self.pipeline = pipeline
        self.config = config
        self.hp = hp or HyperParams()
        self._llm_client: genai.Client | None = None

    @property
    def llm_client(self) -> genai.Client:
        if self._llm_client is None:
            self._llm_client = genai.Client(api_key=self.config.google_api_key)
        return self._llm_client

    def load_test_corpus(self, corpus_path: Path) -> list[TestCase]:
        """Load test cases from a ground_truth.json file."""
        gt_path = corpus_path / "ground_truth.json"
        if not gt_path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

        with open(gt_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases = []
        for item in data.get("test_cases", []):
            cases.append(
                TestCase(
                    query=item["query"],
                    expected_block_ids=item.get("expected_block_ids", []),
                    expected_key_points=item.get("expected_key_points", []),
                    strategy_hint=item.get("strategy_hint", ""),
                    tags=item.get("tags", []),
                )
            )
        return cases

    def run_benchmark(self, test_cases: list[TestCase]) -> BenchmarkReport:
        """Run all test cases and produce an aggregate report."""
        results: list[TestResult] = []
        latencies_by_stage: dict[str, list[float]] = {}

        for case in test_cases:
            result = self._evaluate_single(case)
            results.append(result)

            # Collect latencies
            for stage, seconds in result.latency.items():
                if stage not in latencies_by_stage:
                    latencies_by_stage[stage] = []
                latencies_by_stage[stage].append(seconds)

        # Aggregate metrics
        n = len(results) or 1
        report = BenchmarkReport(
            timestamp=datetime.utcnow().isoformat(),
            total_cases=len(results),
            avg_recall=sum(r.recall_at_k for r in results) / n,
            avg_precision=sum(r.precision_at_k for r in results) / n,
            avg_mrr=sum(r.mrr for r in results) / n,
            avg_ndcg=sum(r.ndcg_at_10 for r in results) / n,
            routing_accuracy=sum(1 for r in results if r.routing_correct) / n,
            avg_faithfulness=sum(r.faithfulness for r in results) / n,
            avg_answer_relevance=sum(r.answer_relevance for r in results) / n,
            avg_coverage=sum(r.coverage for r in results) / n,
            results=results,
        )

        # Compute latency percentiles
        for stage, times in latencies_by_stage.items():
            if times:
                report.latency_p50[stage] = float(np.percentile(times, 50))
                report.latency_p95[stage] = float(np.percentile(times, 95))

        return report

    def _evaluate_single(self, case: TestCase) -> TestResult:
        """Evaluate a single test case."""
        result = TestResult(query=case.query)

        # Run the pipeline
        pipeline_result = self.pipeline.query(case.query)
        result.answer = pipeline_result.answer
        result.strategy_used = pipeline_result.strategy
        result.latency = pipeline_result.latency

        # Get retrieved block IDs from context
        result.blocks_retrieved = []  # Would need pipeline to expose this

        # ── Routing accuracy ─────────────────────────────────────────────
        if case.strategy_hint:
            result.routing_correct = pipeline_result.strategy == case.strategy_hint

        # ── Retrieval metrics ────────────────────────────────────────────
        if case.expected_block_ids:
            retrieved = set(result.blocks_retrieved)
            expected = set(case.expected_block_ids)

            if retrieved:
                result.recall_at_k = (
                    len(retrieved & expected) / len(expected) if expected else 0
                )
                result.precision_at_k = len(retrieved & expected) / len(retrieved)

                # MRR: rank of first relevant result
                for i, bid in enumerate(result.blocks_retrieved, 1):
                    if bid in expected:
                        result.mrr = 1.0 / i
                        break

                # NDCG@10
                result.ndcg_at_10 = self._compute_ndcg(
                    result.blocks_retrieved[:10], expected
                )

        # ── LLM-as-judge metrics ─────────────────────────────────────────
        if case.expected_key_points:
            judge_scores = self._llm_judge(
                query=case.query,
                answer=pipeline_result.answer,
                key_points=case.expected_key_points,
            )
            result.faithfulness = judge_scores.get("faithfulness", 0.0)
            result.answer_relevance = judge_scores.get("relevance", 0.0)
            result.coverage = judge_scores.get("coverage", 0.0)

        return result

    def _compute_ndcg(
        self, ranked_ids: list[str], relevant_ids: set[str], k: int = 10
    ) -> float:
        """Compute NDCG@K."""
        dcg = 0.0
        for i, block_id in enumerate(ranked_ids[:k]):
            rel = 1.0 if block_id in relevant_ids else 0.0
            dcg += rel / np.log2(i + 2)  # i+2 because log2(1) = 0

        # Ideal DCG
        ideal_rels = sorted(
            [1.0 if bid in relevant_ids else 0.0 for bid in ranked_ids[:k]],
            reverse=True,
        )
        idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_rels))

        return dcg / idcg if idcg > 0 else 0.0

    def _llm_judge(
        self, query: str, answer: str, key_points: list[str]
    ) -> dict[str, float]:
        """Use an LLM to judge answer quality."""
        key_points_text = "\n".join(f"- {kp}" for kp in key_points)

        prompt = f"""You are an evaluation judge. Score the following answer on three criteria.

Query: "{query}"

Answer to evaluate:
{answer}

Expected key points that should be covered:
{key_points_text}

Score each criterion from 0.0 to 1.0:
1. "faithfulness": Are all claims in the answer supported by factual information? (1.0 = fully supported, 0.0 = hallucinated)
2. "relevance": How relevant is the answer to the original query? (1.0 = perfectly relevant, 0.0 = off-topic)  
3. "coverage": What fraction of the expected key points are addressed? (1.0 = all covered, 0.0 = none covered)

Return ONLY a JSON object with the three scores, e.g.: {{"faithfulness": 0.8, "relevance": 0.9, "coverage": 0.7}}"""

        try:
            response = self.llm_client.models.generate_content(
                model=self.config.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.hp.judge_temperature,
                    response_mime_type="application/json",
                ),
            )
            content = response.text or "{}"
            scores = json.loads(content)
            return {
                "faithfulness": float(scores.get("faithfulness", 0.0)),
                "relevance": float(scores.get("relevance", 0.0)),
                "coverage": float(scores.get("coverage", 0.0)),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")
            return {"faithfulness": 0.0, "relevance": 0.0, "coverage": 0.0}

    def save_report(self, report: BenchmarkReport, output_dir: Path) -> Path:
        """Save the benchmark report as JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"eval_{report.timestamp.replace(':', '-')}.json"
        output_path = output_dir / filename

        # Convert to serializable dict
        report_dict = {
            "timestamp": report.timestamp,
            "total_cases": report.total_cases,
            "metrics": {
                "avg_recall": report.avg_recall,
                "avg_precision": report.avg_precision,
                "avg_mrr": report.avg_mrr,
                "avg_ndcg": report.avg_ndcg,
                "routing_accuracy": report.routing_accuracy,
                "avg_faithfulness": report.avg_faithfulness,
                "avg_answer_relevance": report.avg_answer_relevance,
                "avg_coverage": report.avg_coverage,
            },
            "latency": {
                "p50": report.latency_p50,
                "p95": report.latency_p95,
            },
            "results": [
                {
                    "query": r.query,
                    "answer": r.answer[:200],  # Truncate for readability
                    "strategy": r.strategy_used,
                    "recall": r.recall_at_k,
                    "precision": r.precision_at_k,
                    "mrr": r.mrr,
                    "ndcg": r.ndcg_at_10,
                    "faithfulness": r.faithfulness,
                    "relevance": r.answer_relevance,
                    "coverage": r.coverage,
                    "latency": r.latency,
                }
                for r in report.results
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Benchmark report saved to {output_path}")
        return output_path

    @staticmethod
    def compare_reports(report_a_path: Path, report_b_path: Path) -> dict[str, Any]:
        """Compare two benchmark reports and show deltas."""
        with open(report_a_path) as f:
            a = json.load(f)
        with open(report_b_path) as f:
            b = json.load(f)

        comparison = {
            "report_a": str(report_a_path),
            "report_b": str(report_b_path),
            "deltas": {},
        }

        a_metrics = a.get("metrics", {})
        b_metrics = b.get("metrics", {})

        for key in a_metrics:
            if key in b_metrics:
                delta = b_metrics[key] - a_metrics[key]
                direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                comparison["deltas"][key] = {
                    "before": a_metrics[key],
                    "after": b_metrics[key],
                    "delta": round(delta, 4),
                    "direction": direction,
                }

        return comparison
