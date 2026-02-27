# GraphRAG — Complete Technical Deep Dive

A comprehensive guide to understanding every concept, algorithm, and design decision in the Context-Aware Agentic GraphRAG system.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [Core Concepts You Need to Know](#2-core-concepts-you-need-to-know)
3. [Data Layer — schema.py](#3-data-layer--schemapy)
4. [Embedding Pipeline — embeddings.py](#4-embedding-pipeline--embeddingspy)
5. [Hybrid Retrieval — search.py](#5-hybrid-retrieval--searchpy)
6. [Edge Inference — edges.py](#6-edge-inference--edgespy)
7. [Incremental Indexing — indexer.py](#7-incremental-indexing--indexerpy)
8. [Graph Traversal — graph.py](#8-graph-traversal--graphpy)
9. [Reranking — reranker.py](#9-reranking--rerankerpy)
10. [Agentic Router — router.py](#10-agentic-router--routerpy)
11. [Context Assembly — context.py](#11-context-assembly--contextpy)
12. [LLM Synthesis — llm.py](#12-llm-synthesis--llmpy)
13. [Pipeline Orchestrator — commands.py](#13-pipeline-orchestrator--commandspy)
14. [Evaluation — evaluation.py](#14-evaluation--evaluationpy)
15. [The Full Query Flow (End to End)](#15-the-full-query-flow-end-to-end)
16. [Key Design Decisions Explained](#16-key-design-decisions-explained)

---

## 1. The Big Picture

### What is RAG?

**Retrieval-Augmented Generation (RAG)** is a technique where, instead of relying solely on an LLM's training data, you first *retrieve* relevant documents from your own data, then feed them to the LLM as context. This means the LLM can answer questions about **your** notes — data it was never trained on.

```
Traditional LLM:    Query → LLM → Answer (from training data only)
RAG:                Query → Retrieve relevant docs → LLM + docs → Answer (from YOUR data)
```

### What is GraphRAG?

Standard RAG retrieves documents by similarity (e.g., "find the 10 most similar paragraphs"). **GraphRAG** goes further by building a **knowledge graph** of relationships between your notes and traversing those relationships to assemble richer context.

```
Standard RAG:   Query → Find similar chunks → LLM
GraphRAG:       Query → Find similar chunks → Follow relationships → Build connected context → LLM
```

### Why Graph + RAG?

Consider this: you have a note about "Neural Networks" and another about "Gradient Descent." They're separate notes, but they're deeply related. A keyword search for "how do neural networks learn?" might find the neural networks note but miss the gradient descent note. GraphRAG connects them via edges (shared tags, backlinks, semantic similarity) and traverses those connections to build a more complete picture.

### System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Query                                  │
│                     "How does X relate to Y?"                       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Agentic Router  │  ← Classifies query complexity
                    │   (router.py)    │     and rewrites it for search
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │      Hybrid Retrieval        │
              │       (search.py)            │
              ├──────────┬──────────────┤
              │          │              │
     ┌────────▼───┐  ┌──▼───────┐      │
     │  SQLite     │  │  FAISS   │      │
     │  FTS5       │  │  Vector  │      │
     │  (keyword)  │  │  Search  │      │
     └────────┬───┘  └──┬───────┘      │
              │          │              │
              └──────────▼──────────────┘
                         │
                ┌────────▼────────┐
                │  RRF Fusion     │  ← Merges keyword + semantic results
                └────────┬────────┘
                         │
                ┌────────▼────────┐
                │   Reranker      │  ← LLM scores relevance 0-10
                │  (reranker.py)  │
                └────────┬────────┘
                         │
           ┌─────────────┼─────────────┐
           │ Direct Recall │  Contextual │
           │               │  Traversal  │
           │               │             │
           │         ┌─────▼─────┐       │
           │         │  A* Graph  │      │
           │         │  Traversal │      │
           │         │ (graph.py) │      │
           │         └─────┬─────┘      │
           └───────────────┼─────────────┘
                           │
                  ┌────────▼────────┐
                  │ Context Assembly │  ← Stitches blocks into prompt
                  │  (context.py)   │     with token budget
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  Gemini LLM     │  ← Generates final answer
                  │   (llm.py)      │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │     Answer       │
                  └──────────────────┘
```

---

## 2. Core Concepts You Need to Know

### 2.1 Embeddings

An **embedding** is a numerical representation of text — a list of numbers (a "vector") that captures the *meaning* of the text. Similar texts produce similar vectors.

```
"Machine learning is great"  →  [0.23, -0.45, 0.87, 0.12, ...]   (768 numbers)
"AI is awesome"              →  [0.21, -0.43, 0.85, 0.14, ...]   (similar vector!)
"I like pizza"               →  [0.92, 0.11, -0.33, 0.67, ...]   (very different vector)
```

We use Google's `gemini-embedding-001` model, which produces 768-dimensional vectors.

**Why 768 numbers?** The model was trained to encode semantic meaning across 768 independent dimensions. More dimensions = more nuance, but more storage/compute. 768 is a good balance.

### 2.2 Cosine Similarity

To measure how "similar" two vectors are, we use **cosine similarity** — the cosine of the angle between them.

```
cos(θ) = (A · B) / (|A| × |B|)

Where:
  A · B   = dot product (sum of element-wise multiplication)
  |A|     = magnitude (L2 norm) of A
```

- **1.0** = identical direction (same meaning)
- **0.0** = perpendicular (unrelated)
- **-1.0** = opposite direction

**Shortcut:** If both vectors are L2-normalized (magnitude = 1), then cosine similarity equals the dot product. That's why we normalize vectors before storing them in FAISS.

### 2.3 FAISS (Facebook AI Similarity Search)

**FAISS** is a library for fast nearest-neighbor search in high-dimensional vector spaces. Think of it as a specialized database optimized for "find me the 10 vectors most similar to this query vector."

We use `IndexFlatIP` (Inner Product), which:
- Stores vectors in a flat array (no compression)
- Computes exact inner product (= cosine similarity when vectors are normalized)
- Is simple and accurate (no approximation)

**Why not a fancier index?** For our scale (thousands of note blocks, not millions), flat search is fast enough and guarantees exact results.

### 2.4 BM25 / FTS5

**BM25** is the classic keyword-matching algorithm (the one behind Google Search circa 2000). It scores documents based on:
- **Term Frequency (TF):** How often the search term appears in the document
- **Inverse Document Frequency (IDF):** How rare the term is across all documents
- **Document Length:** Shorter documents that match get a boost

**FTS5** is SQLite's built-in full-text search engine. It implements BM25 under the hood. We use it with the **Porter stemmer** (so "running" matches "run") and **unicode61** tokenizer (handles non-ASCII text).

```sql
-- This is how FTS5 works behind the scenes:
SELECT * FROM blocks_fts WHERE blocks_fts MATCH 'machine learning'
ORDER BY bm25(blocks_fts)  -- Lower = more relevant (SQLite quirk)
```

### 2.5 Reciprocal Rank Fusion (RRF)

When you have two ranked lists from different sources (keyword search and semantic search), how do you merge them? You can't just average the raw scores because BM25 scores and cosine similarity scores are on completely different scales.

**RRF** solves this elegantly by only using **rank positions**, not raw scores:

```
RRF_score(doc) = Σ 1/(k + rank_i)

Where:
  k = 60 (constant from the original paper)
  rank_i = the document's position in each ranked list
```

**Example:**
```
Document "block-A" is ranked #1 in FTS5 and #3 in FAISS:
  RRF = 1/(60+1) + 1/(60+3) = 0.01639 + 0.01587 = 0.03226

Document "block-B" is ranked #5 in FTS5 and #1 in FAISS:
  RRF = 1/(60+5) + 1/(60+1) = 0.01538 + 0.01639 = 0.03177

Document "block-C" is ranked #2 in FTS5 only (not in FAISS):
  RRF = 1/(60+2) = 0.01613
```

Block-A wins because it ranks well in **both** systems. This is the power of RRF — a document that's good in both keyword and semantic is better than one that's great in only one.

### 2.6 A* Search Algorithm

**A\*** is a pathfinding algorithm that finds the optimal path from a start node to a goal node. It uses:

```
f(n) = g(n) + h(n)

Where:
  f(n) = total estimated cost through node n
  g(n) = actual cost from start to n (sum of edge weights)
  h(n) = heuristic: estimated cost from n to goal
```

The algorithm maintains a **priority queue** ordered by f(n), always expanding the most promising node first.

**In our system,** we adapt A* for exploration (no single goal node):
- **g(n):** Sum of edge weights traversed (backlinks = 0.1, same_note = 0.2, shared_tag = 0.3, semantic = 0.5)
- **h(n):** `1 - cosine_similarity(node_embedding, query_embedding)` — how far this node is from the query in semantic space
- **Goal:** Find the path to the most query-relevant nodes reachable from entry points

**Why is the heuristic admissible?** Because cosine similarity is bounded [0, 1], so h(n) ∈ [0, 1]. Edge weights are also in [0, 1]. This means h(n) never overestimates the true cost, which is the admissibility requirement for A* to find optimal paths.

### 2.7 Knowledge Graph

A **knowledge graph** is a network where:
- **Nodes** = Things (in our case, note blocks)
- **Edges** = Relationships between things

Our graph has four types of edges:

| Edge Type | Weight | Source | Example |
|-----------|--------|--------|---------|
| `backlink` | 0.1 (strongest) | Explicit user link | Block A references block B |
| `same_note` | 0.2 | Auto-inferred | Blocks in the same .jnote file |
| `shared_tag` | 0.3 | Auto-inferred | Both tagged "machine-learning" |
| `semantically_similar` | 0.5 (weakest) | Auto-inferred | Cosine similarity > 0.85 |

**Lower weight = stronger relationship = lower traversal cost.** This means A* prefers paths through backlinks over paths through semantic similarity.

---

## 3. Data Layer — schema.py

This module defines the SQLite database that stores everything persistently.

### Database Tables

```
┌──────────────────┐     ┌──────────────────┐
│     blocks       │     │     edges        │
├──────────────────┤     ├──────────────────┤
│ block_id    (PK) │◄────│ source_block_id  │
│ note_id          │     │ target_block_id  │──►│blocks│
│ note_path        │     │ relation_type    │
│ content          │     │ weight           │
│ block_type       │     │ is_inferred      │
│ content_hash     │     └──────────────────┘
│ last_indexed_at  │
└──────────────────┘
         │
         │ (sync via triggers)
         ▼
┌──────────────────┐     ┌──────────────────┐
│   blocks_fts     │     │ embeddings_meta  │
│  (FTS5 virtual)  │     ├──────────────────┤
├──────────────────┤     │ block_id         │
│ block_id         │     │ faiss_position   │
│ content          │     │ model_version    │
└──────────────────┘     │ is_active        │◄── tombstone flag
                         └──────────────────┘
```

### Key Design: Content-Synced FTS5

The `blocks_fts` table is a **virtual table** — it doesn't store data normally. Instead, SQLite maintains an inverted index optimized for text search. Three **triggers** keep it in sync:

```sql
-- When a block is INSERTED, copy its content to FTS5:
AFTER INSERT ON blocks → INSERT INTO blocks_fts(...)

-- When a block is DELETED, tell FTS5 to remove it:
AFTER DELETE ON blocks → INSERT INTO blocks_fts(blocks_fts, ...) VALUES('delete', ...)

-- When a block is UPDATED, delete the old entry and insert the new one:
AFTER UPDATE ON blocks → delete old + insert new
```

This means you never need to manually sync FTS5 — it's always up to date.

### Key Design: WAL Mode

```python
self._conn.execute("PRAGMA journal_mode=WAL")
```

**WAL (Write-Ahead Logging)** allows concurrent reads and writes. Without WAL, a write operation would block all reads. With WAL, readers see a consistent snapshot while writers append to a log. This matters because the background indexer daemon writes while the search reads.

### RAGConfig Dataclass

The `RAGConfig` uses Python's `@dataclass` with sensible defaults, loaded from `rag_config.json`:

```python
@dataclass
class RAGConfig:
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    llm_model: str = "gemini-2.0-flash"
    google_api_key: str = ""
    similarity_threshold: float = 0.85
    tombstone_compaction_ratio: float = 0.20
    # ... etc
```

The `load()` classmethod reads JSON and only applies keys that match dataclass fields — this is forward-compatible (new config keys don't crash old code).

---

## 4. Embedding Pipeline — embeddings.py

This module converts text into vectors and manages the FAISS index.

### EmbeddingClient

Wraps the Google Gemini API for generating embeddings:

```python
# What happens when you embed text:
response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=["Machine learning is great", "I like pizza"]
)
# response.embeddings[0].values → [0.23, -0.45, 0.87, ...]  (768 floats)
# response.embeddings[1].values → [0.92, 0.11, -0.33, ...]  (768 floats)
```

**Batch embedding** sends multiple texts in one API call — much faster than one-at-a-time.

### FAISSIndex

The FAISS index is an **append-only** flat vector store:

```
Index state after adding 3 blocks:
Position 0: [0.23, -0.45, ...]  → block-aaa
Position 1: [0.67, 0.12, ...]   → block-bbb
Position 2: [0.89, -0.33, ...]  → block-ccc
```

**L2 Normalization:** Before adding vectors, we normalize them so each has magnitude 1:

```python
faiss.normalize_L2(vectors)  # Now |v| = 1 for all vectors
```

This converts inner product search into cosine similarity search (since cos(A,B) = A·B when |A|=|B|=1).

**Search:** Given a query vector, FAISS returns the k positions with highest inner product:

```python
scores, indices = self.index.search(query_vector, k=10)
# indices[0] = [2, 0, 1]  → positions of top-3 matches
# scores[0]  = [0.95, 0.82, 0.61]  → similarity scores
```

### EmbeddingManager

Ties the embedding client, FAISS index, and database metadata together:

```
embed_and_store("block-aaa", "Machine learning is great")
  ├── 1. Call Gemini API → get vector [0.23, -0.45, ...]
  ├── 2. Normalize and add to FAISS → position 0
  └── 3. Store metadata in SQLite: (block_id="block-aaa", faiss_position=0, is_active=1)
```

**Tombstone mechanism** (covered in detail in §7):

```
tombstone_block("block-aaa")
  └── SQLite: UPDATE embeddings_meta SET is_active=0 WHERE block_id='block-aaa'
  
  # The vector at position 0 is still in FAISS, but search() will ignore it
  # because it only returns results at positions that are in the 'active' set
```

---

## 5. Hybrid Retrieval — search.py

This is where keyword search and semantic search come together.

### Why Hybrid?

Neither keyword nor semantic search is perfect alone:

| Query | Keyword (FTS5) wins | Semantic (FAISS) wins |
|-------|--------------------|-----------------------|
| "ActiveNote Manager" | ✅ Exact term match | ❌ Might match "NotebookController" |
| "how to train models" | ❌ Misses "fitting algorithms" | ✅ Captures semantic meaning |
| "API key configuration" | ✅ Finds exact phrase | ✅ Also works semantically |

Hybrid search gives you the best of both worlds.

### The Three-Step Process

```python
def search(self, query, top_k=50):
    # Step 1: FTS5 → Ranked list A (by BM25)
    fts_results = self._fts_search(query, limit=top_k * 2)
    
    # Step 2: FAISS → Ranked list B (by cosine similarity)
    semantic_results = self._semantic_search(query, limit=top_k * 2)
    
    # Step 3: RRF Fusion → Merged ranked list
    merged = self._rrf_fuse(fts_results, semantic_results)
    merged.sort(key=lambda r: r.rrf_score, reverse=True)
    return merged[:top_k]
```

**Why `limit=top_k * 2`?** We fetch 2x candidates from each source so that after fusion, we still have enough results even if there's little overlap.

### RRF Implementation Detail

```python
for result in results_by_id.values():
    rrf = 0.0
    if result.fts_rank is not None:
        rrf += 1.0 / (60 + result.fts_rank)
    if result.semantic_rank is not None:
        rrf += 1.0 / (60 + result.semantic_rank)
    result.rrf_score = rrf
```

A document only in FTS5 gets one term; a document only in FAISS gets one term; a document in **both** gets the sum of both terms. This naturally boosts documents that appear in both search modalities.

---

## 6. Edge Inference — edges.py

This module builds the knowledge graph's edges from .jnote files.

### .jnote File Structure

```json
{
  "metadata": {"note_id": "abc123", "title": "My Note"},
  "blocks": [
    {
      "block_id": "block-001",
      "type": "text",
      "data": {"content": "Machine learning is..."},
      "tags": ["ai", "ml"],
      "backlinks": ["block-xyz"]
    }
  ]
}
```

Each block can have:
- **Tags:** Keywords the user assigned
- **Backlinks:** References to other block IDs (user-created cross-references)

### Three Types of Explicit Edges

**1. Same-Note Edges (weight 0.2):**
All blocks within the same .jnote file are considered related:
```
Block A ──same_note──► Block B
Block A ──same_note──► Block C
Block B ──same_note──► Block A
Block B ──same_note──► Block C
... (all pairs)
```

**2. Backlink Edges (weight 0.1 — strongest):**
When a block explicitly references another block. These are **bidirectional**:
```
Block A has backlinks: ["block-xyz"]
→ Block A ──backlink──► block-xyz
→ block-xyz ──backlink──► Block A
```

**3. Shared Tag Edges (weight 0.3):**
When two blocks share any tag:
```
Block A tags: ["ai", "ml"]
Block B tags: ["ai", "dl"]
Shared: {"ai"}
→ Block A ──shared_tag──► Block B
```

### Semantic Edges (weight 0.5)

These are auto-inferred by comparing embedding vectors:

```python
similarities = all_vecs_norm @ block_vec_norm  # Cosine similarity with all other blocks
for other_id, sim in zip(all_block_ids, similarities):
    if sim >= 0.85:  # threshold
        create_edge(block_id, other_id, "semantically_similar", 0.5)
```

**Why 0.85 threshold?** This is a tunable parameter. Too low (0.5) → too many edges, noisy graph. Too high (0.95) → too few edges, disconnected graph. 0.85 is a good starting point.

---

## 7. Incremental Indexing — indexer.py

The most engineering-heavy module. Solves: "How do you efficiently update the index when a user edits a note?"

### The Problem

When a user edits a note:
1. Some blocks are unchanged (don't re-embed)
2. Some blocks are modified (need new embeddings)
3. Some blocks are new (need embeddings)
4. Some blocks were deleted (need cleanup)

And FAISS **doesn't support in-place updates** — you can't replace the vector at position 5. You can only append.

### The Solution: Tombstone + Append + Compaction

```
Initial state:
FAISS:  [vec0, vec1, vec2, vec3, vec4]
SQLite: block-A→pos0(active), block-B→pos1(active), block-C→pos2(active)

User edits block-B:
Step 1 - Tombstone old: mark pos1 as inactive in SQLite
Step 2 - Append new:    add new vec5 to FAISS
Step 3 - Record:        block-B→pos5(active)

After edit:
FAISS:  [vec0, vec1(dead), vec2, vec3, vec4, vec5]
SQLite: block-A→pos0(active), block-B→pos1(inactive), block-B→pos5(active), block-C→pos2(active)

Search filters out pos1 automatically (only queries active positions).
```

### Change Detection: SHA-256 Hashing

```python
def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

For each block, we compare the current content hash against the stored hash:

```python
old_hash = existing_hashes.get(block["block_id"])
new_hash = content_hash(block["content"])

if old_hash is None:          → NEW block
elif old_hash != new_hash:    → MODIFIED block
else:                          → UNCHANGED (skip)
```

This is fast (no API calls needed) and deterministic.

### Compaction

Over time, tombstoned entries accumulate. When >20% are tombstoned, we **compact**:

```python
def compact(self):
    # 1. Get all active embeddings from SQLite
    # 2. Reconstruct their vectors from FAISS
    # 3. Build a brand new FAISS index from just the active vectors
    # 4. Clear all SQLite metadata and re-insert with new positions
```

After compaction, the FAISS index is clean — no dead entries.

### The Indexer Daemon

Background thread that reacts to file saves:

```
User saves note → Watchdog fires on_note_saved()
                       │
                       ▼
              ┌────────────────┐
              │   Debounce     │  Wait 2 seconds (configurable)
              │   Timer        │  in case user saves again quickly
              └────────┬───────┘
                       │ (2 seconds pass without another save)
                       ▼
              ┌────────────────┐
              │  Enqueue note  │  Add to index_queue in SQLite
              │  in DB queue   │  with status='pending'
              └────────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  Background    │  Daemon loop picks up pending items
              │  Worker Loop   │  and runs incremental_update()
              └────────────────┘
```

**Why debounce?** When a user types, auto-save might fire many times per second. Debouncing waits for a quiet period before triggering the expensive re-index.

---

## 8. Graph Traversal — graph.py

This module builds an in-memory graph and runs A* traversal to discover connected context.

### NetworkX DiGraph

We use a **directed graph** (DiGraph) because edge semantics are directional — "A links to B" is different from "B links to A" (though backlinks create edges in both directions).

```python
# Building the graph from database edges:
for edge in db.get_all_edges():
    graph.add_edge(
        edge["source_block_id"],
        edge["target_block_id"],
        weight=edge["weight"],          # 0.1 to 0.5
        relation_type=edge["relation_type"]  # backlink, same_note, etc.
    )
```

### Multi-Entry A* Traversal

Traditional A* goes from point A to point B. Our variant:
1. **No single goal** — we want to *explore* relevantly, not reach a specific node
2. **Multiple starting points** — we start from the top-K reranked blocks
3. **Semantic heuristic** — h(n) guides us toward query-relevant nodes

```python
def astar_traverse(self, entry_node_ids, query_embedding, max_nodes=100):
    for entry_id in entry_node_ids:
        path = self._astar_from_node(entry_id, query_embedding, ...)
        result.paths.append(path)
        result.visited_nodes.update(path)
```

### The Heuristic: h(n) = 1 - cos(n, query)

```python
def heuristic(node_id):
    vec = get_node_embedding(node_id)
    sim = dot(query_embedding, vec)  # cosine similarity (vectors are normalized)
    return max(0.0, 1.0 - sim)       # 0 = perfectly relevant, 1 = totally irrelevant
```

This means:
- A node whose embedding is identical to the query has h=0 (we're "at the goal")
- A node with nothing in common has h=1 (maximum estimated cost)
- A* will prefer expanding nodes with low h first (more relevant to the query)

### The Priority Queue (Open Set)

```python
open_set = []  # Min-heap of (f_score, node_id, path)

# Start: push entry node with f = 0 + h(start)
heapq.heappush(open_set, (h_start, start_id, [start_id]))

while open_set and nodes_explored < max_nodes:
    f_score, current, path = heapq.heappop(open_set)  # Pop lowest f
    
    # Track best path (lowest heuristic = most relevant destination)
    if h(current) < best_score:
        best_path = path
    
    # Expand neighbors
    for neighbor in graph.neighbors(current):
        g_new = f_score - h(current) + edge_weight  # g = f - h + edge
        h_new = h(neighbor)
        f_new = g_new + h_new
        heapq.heappush(open_set, (f_new, neighbor, path + [neighbor]))
```

**The result:** A path from the entry node through the graph, following edges toward the most query-relevant blocks. This discovers blocks that are related to your query *through their connections*, not just their individual similarity.

---

## 9. Reranking — reranker.py

After hybrid search returns ~50 candidates, the reranker narrows it down to the top ~10 using deeper analysis.

### Why Rerank?

Hybrid search is fast but shallow — it uses keyword matching and vector similarity. Reranking uses an **LLM to read each candidate** and judge how relevant it actually is to the query. This catches nuances that pure similarity misses.

### LLM-as-Judge Approach

```python
prompt = """Score each passage's relevance to the query on 0-10.
Query: "how do neural networks learn?"

[0] Machine learning uses gradient descent for optimization...
[1] The restaurant menu includes pasta and salads...
[2] Backpropagation computes gradients layer by layer...

Return JSON: [{"index": 0, "score": 8}, {"index": 1, "score": 0}, {"index": 2, "score": 9}]"""
```

The LLM reads the actual text and understands context, synonyms, and relevance at a much deeper level than vector similarity.

**Scores are normalized to [0, 1]** by dividing by 10, making them comparable across queries.

**Fallback:** If the API call fails, we fall back to the RRF scores from hybrid search.

---

## 10. Agentic Router — router.py

The "brain" that decides how to handle each query.

### Two Strategies

| Strategy | When | Example Query |
|----------|------|---------------|
| `direct_recall` | Simple, factual queries | "What is gradient descent?" |
| `contextual_traversal` | Complex, multi-concept queries | "How does gradient descent relate to neural network training?" |

### How It Decides

The router sends the query to Gemini with a classification prompt:

```python
prompt = f"""Analyze this query:
User Query: "{query}"

Return JSON:
  strategy: "direct_recall" or "contextual_traversal"
  optimized_query: rewritten for better search
  sub_queries: decomposed sub-queries (for traversal only)"""
```

**Example output:**
```json
{
  "strategy": "contextual_traversal",
  "reasoning": "Query asks about relationship between two concepts",
  "optimized_query": "relationship between gradient descent optimization and neural network training convergence",
  "sub_queries": [
    "What is gradient descent and how does it work?",
    "How are neural networks trained?",
    "What role does gradient descent play in neural network training?"
  ]
}
```

### Query Optimization

The optimized query is what actually gets sent to hybrid search. It's more specific and descriptive than what the user typed, which improves both FTS5 and FAISS retrieval quality.

```
User types:     "how do NNs learn?"
Optimized:      "how do neural networks learn through training with backpropagation and gradient descent optimization"
```

---

## 11. Context Assembly — context.py

This module takes the retrieved/traversed blocks and assembles them into a text prompt for the LLM.

### Token Budget Management

LLMs have token limits. We can't send all 50 retrieved blocks — we'd blow the context window. The assembler respects a configurable budget (default: 4000 tokens ≈ 16,000 characters):

```python
CHARS_PER_TOKEN = 4  # Rough approximation

for block in sorted_by_relevance:
    section = format_block(block)
    if total_chars + len(section) > max_chars:
        truncated = True
        break
    sections.append(section)
```

### Block Formatting

Each block gets a header showing its source note and relevance:

```
--- [my-research-notes] (relevance: 0.92) ---
Machine learning is a subset of artificial intelligence that focuses on
building systems that learn from data...

--- [deep-learning-intro] (relevance: 0.87) ---
Neural networks consist of layers of interconnected nodes...
```

### Two Assembly Paths

1. **From Traversal** (contextual queries): Blocks are sorted by their A* relevance scores
2. **From Reranking** (direct queries): Blocks are sorted by reranker scores

Both produce the same output format — an `AssembledContext` with the stitched text, block IDs, token estimate, and truncation flag.

---

## 12. LLM Synthesis — llm.py

The final stage: send the assembled context to Gemini and get an answer.

```python
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=context.context_text,   # The assembled blocks + query
    config=GenerateContentConfig(
        temperature=0.3,              # Slightly creative but mostly factual
        system_instruction=system_prompt  # "You are a helpful notes assistant..."
    ),
)
```

**Temperature 0.3:** Low enough to be factual (good for answering from notes), but not 0.0 (which can be too rigid). This is a sweet spot for RAG.

**Usage tracking:** We capture token counts from `response.usage_metadata` for monitoring costs and performance.

---

## 13. Pipeline Orchestrator — commands.py

This is where everything comes together. The `RAGPipeline` class wires all components and exposes a clean API.

### Initialization

```python
pipeline = RAGPipeline(config, data_dir)
# Creates:
#   - RAGDatabase (SQLite)
#   - EmbeddingManager (Gemini API + FAISS)
#   - EdgeInference
#   - HybridSearch
#   - Reranker
#   - AgenticRouter
#   - KnowledgeGraph (NetworkX)
#   - ContextAssembler
#   - LLMClient (Gemini)
#   - Indexer
```

### Query Pipeline Flow

```python
result = pipeline.query("How does X relate to Y?")
```

Internally:
```
1. routing  = router.route(query)         → CONTEXTUAL_TRAVERSAL, optimized_query
2. candidates = search.search(optimized)  → 50 blocks from FTS5+FAISS+RRF
3. reranked = reranker.rerank(optimized)  → Top 10 by LLM-as-judge
4. traversal = graph.astar_traverse(...)  → Connected blocks via A*
5. context  = assembler.assemble(...)     → Token-budgeted prompt
6. response = llm.synthesize(context)     → Final answer
```

Each stage is timed independently:
```python
latency = {
    "routing": 0.45,       # LLM call
    "retrieval": 0.12,     # FTS5 + FAISS (fast, local)
    "reranking": 1.20,     # LLM call
    "traversal": 0.03,     # In-memory graph (very fast)
    "assembly": 0.001,     # String formatting (instant)
    "llm": 0.85,           # LLM call
    "total": 2.65          # seconds
}
```

---

## 14. Evaluation — evaluation.py

How do you know if the system is working well? The evaluation harness measures quality rigorously.

### Golden Test Corpus

A `ground_truth.json` file contains test cases with expected answers:

```json
{
  "query": "What blocks are tagged with summary?",
  "expected_block_ids": ["block-aaa", "block-bbb"],
  "expected_key_points": ["Multiple blocks have the summary tag"],
  "strategy_hint": "direct_recall"
}
```

### Metrics Explained

**Recall@K:** Of all the blocks that *should* be retrieved, what fraction *was* retrieved?
```
Expected: {A, B, C}    Retrieved: {A, C, D, E}
Recall = |{A,C}| / |{A,B,C}| = 2/3 = 0.667
```

**Precision@K:** Of all retrieved blocks, what fraction was actually relevant?
```
Precision = |{A,C}| / |{A,C,D,E}| = 2/4 = 0.5
```

**MRR (Mean Reciprocal Rank):** Where did the first relevant result appear?
```
Retrieved: [D, A, E, C]  → First relevant (A) is at position 2
MRR = 1/2 = 0.5
```

**NDCG@10 (Normalized Discounted Cumulative Gain):** Measures the quality of ranking — are relevant results near the top?
```
DCG = Σ rel_i / log2(i + 2)
NDCG = DCG / ideal_DCG
```

**Faithfulness (LLM-judged):** Are all claims in the answer supported by the retrieved notes? (0-1)

**Answer Relevance (LLM-judged):** Is the answer actually addressing the query? (0-1)

**Coverage (LLM-judged):** What fraction of expected key points does the answer cover? (0-1)

---

## 15. The Full Query Flow (End to End)

Let's trace a real query through the entire system:

### Query: "How do the different blocks in my love-this-shit note relate to each other?"

**Step 1 — Router:**
```
Strategy: contextual_traversal (asks about relationships → needs graph)
Optimized query: "relationships and connections between blocks in the
                  love-this-shit note, including shared tags and content links"
```

**Step 2 — Hybrid Search:**
```
FTS5 results (keyword match "love-this-shit", "blocks", "relate"):
  Rank 1: block-8cd31c6c (text block about actual content)
  Rank 2: block-af176423 (ActiveNote Manager update)
  Rank 3: block-35e03b29 (Second Block)

FAISS results (semantic similarity to optimized query):
  Rank 1: block-8cd31c6c (score 0.89)
  Rank 2: block-573393d2 (code block, score 0.72)
  Rank 3: block-af176423 (score 0.68)

RRF Fusion:
  block-8cd31c6c: 1/(60+1) + 1/(60+1) = 0.0328  ← top (in both!)
  block-af176423: 1/(60+2) + 1/(60+3) = 0.0320
  block-573393d2: 1/(60+2) = 0.0161
  block-35e03b29: 1/(60+3) = 0.0159
```

**Step 3 — Reranker:**
```
Gemini scores each candidate 0-10:
  block-8cd31c6c: 8/10 = 0.80
  block-af176423: 7/10 = 0.70
  block-35e03b29: 6/10 = 0.60
  block-573393d2: 5/10 = 0.50
```

**Step 4 — A* Traversal:**
```
Entry nodes: [block-8cd31c6c, block-af176423]

From block-8cd31c6c:
  h = 1 - cos(embedding, query) = 0.11 (very relevant)
  Neighbors: block-af176423 (same_note, w=0.2), block-35e03b29 (shared_tag, w=0.3)
  
  Expand to block-af176423: f = 0.2 + 0.30 = 0.50
  Expand to block-35e03b29: f = 0.3 + 0.40 = 0.70
  
  → Follows path: 8cd31c6c → af176423 → 35e03b29

Result: visited {8cd31c6c, af176423, 35e03b29, 573393d2}
```

**Step 5 — Context Assembly:**
```
--- [love-this-shit] (relevance: 0.89) ---
This is actual text content of the note...

--- [love-this-shit] (relevance: 0.70) ---
Updated via ActiveNote Manager...

--- [love-this-shit] (relevance: 0.60) ---
This is another body block...

(Token budget: 1,200 / 4,000 used)
```

**Step 6 — LLM Synthesis:**
```
"The love-this-shit note contains four interconnected blocks:
 1. A main text block with the note's actual content
 2. A block updated via the ActiveNote Manager
 3. A second text block ('Second Block')
 4. A Python code block (print 'Hello World!')

 These blocks are related through shared tags ('summary', 'todo')
 and by being in the same note. The first and third blocks share
 the most tags, suggesting they cover related topics."
```

---

## 16. Key Design Decisions Explained

### Why SQLite + FAISS + NetworkX (not a single database)?

| Component | Purpose | Why this tool? |
|-----------|---------|----------------|
| SQLite | Structured data, FTS5, metadata | Zero-config, embedded, battle-tested |
| FAISS | Vector similarity search | Purpose-built for this, very fast |
| NetworkX | In-memory graph + A* | Pure Python, no server, easy A* |

A single tool (like Neo4j or Pinecone) would require a running server. Our approach: **zero external services** — everything runs in-process.

### Why API for Embeddings (not local models)?

Local embedding models (like sentence-transformers) need ~500MB of RAM and a GPU for decent speed. The Gemini API:
- ~0ms startup time
- No RAM/GPU usage on the user's machine
- Better quality embeddings than most local models
- ~$0.000025 per 1000 tokens (essentially free)

### Why Tombstone + Append (not in-place FAISS update)?

FAISS `IndexFlatIP` doesn't support deletion or replacement. Alternatives:
1. **Rebuild from scratch on every edit** — too slow (re-embeds everything)
2. **Use IndexIDMap** — slower search, more complexity
3. **Tombstone + periodic compaction** — ✅ Simple, fast search, amortized rebuild cost

### Why RRF (not learned fusion)?

Learned fusion (training a model to combine scores) requires labeled training data and is query-distribution-specific. RRF:
- Requires no training data
- Works well out of the box
- Is the industry standard (used by Elasticsearch, Azure AI Search, etc.)
- Has a single tunable parameter (k=60)

### Why A* (not BFS/DFS/PageRank)?

| Algorithm | Problem |
|-----------|---------|
| BFS | Explores all neighbors equally — no query awareness |
| DFS | Goes deep in random directions — no quality guarantee |
| PageRank | Global importance, not query-specific |
| **A*** | **Query-aware, optimal paths, respects edge weights** |

A* with our semantic heuristic naturally gravitates toward query-relevant parts of the graph. It won't waste time exploring the "cooking recipes" neighborhood when you're asking about "machine learning."

---

> **End of Document.** This covers every module, algorithm, and design decision in the GraphRAG pipeline. For the actual source code, see the `rag/` directory. For running the system, see `README.md`.
