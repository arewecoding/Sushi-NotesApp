# Vadapav RAG Module — Setup & Dependencies

Context-Aware Agentic GraphRAG system for the Vadapav notes app.  
Uses **Google Gemini API** for embeddings, reranking, and LLM synthesis.

---

## Quick Start

### 1. Create & activate the virtual environment

```bash
# Create venv
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Windows CMD)
.\.venv\Scripts\activate.bat

# Activate (Linux/macOS)
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API key

Edit `rag_config.json` and add your Google AI API key:

```json
{
    "google_api_key": "YOUR_GOOGLE_AI_API_KEY_HERE"
}
```

Get a key at: https://aistudio.google.com/apikey

### 4. Build the index

```python
from rag.commands import create_pipeline
from pathlib import Path

pipeline = create_pipeline()
stats = pipeline.build_index(Path("path/to/your/notes"))
print(stats)
```

### 5. Query

```python
result = pipeline.query("What are my notes about machine learning?")
print(result.answer)
print(f"Strategy: {result.strategy}")
print(f"Latency: {result.latency}")
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `google-genai` | ≥1.0.0 | Google Gemini API — embeddings, LLM, reranking |
| `faiss-cpu` | ≥1.7.4 | Vector similarity search (local, lightweight) |
| `networkx` | ≥3.0 | In-memory knowledge graph + A* traversal |
| `httpx` | ≥0.25.0 | HTTP client for external API calls |
| `numpy` | ≥1.24.0 | Numerical operations for embeddings |
| `pytest` | ≥8.0.0 | Testing framework |

**Local footprint:** ~20MB. No heavy ML models — all inference goes through Google API.

---

## Project Structure

```
rag/
├── schema.py       # SQLite schema, migrations, config loader
├── embeddings.py   # Google Gemini embedding pipeline + FAISS index
├── search.py       # Hybrid retrieval (FTS5 + FAISS + RRF fusion)
├── edges.py        # Edge inference (tags, backlinks, semantic similarity)
├── indexer.py      # Incremental re-indexing (tombstone + append)
├── graph.py        # NetworkX DiGraph + A* traversal engine
├── reranker.py     # Gemini LLM-as-judge reranking
├── router.py       # Agentic router (direct recall vs graph traversal)
├── context.py      # Context assembly with token budget
├── llm.py          # Gemini LLM integration for answer synthesis
├── commands.py     # Pipeline orchestrator + IPC-ready commands
└── evaluation.py   # Benchmarking harness with LLM-as-judge metrics
```

---

## Models Used

| Task | Model | Notes |
|------|-------|-------|
| Embeddings | `gemini-embedding-001` | 768-dim vectors |
| LLM / Reranking / Routing | `gemini-2.0-flash` | Fast, cheap |

All configurable via `rag_config.json`.

---

## Running Tests

```bash
# Activate venv first
.\.venv\Scripts\Activate.ps1

# Run unit tests
python -m pytest tests/test_rag_pipeline.py -v

# Run benchmark evaluation
python tests/benchmark_rag.py --corpus tests/eval_corpus/ --verbose
```
