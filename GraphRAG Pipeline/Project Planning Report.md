# Context-Aware Agentic GraphRAG

## 1. Problem Statement

Standard Retrieval-Augmented Generation (RAG) relies on vector similarity (like $k$-Nearest Neighbors) to fetch information. While effective for isolated facts, this approach fails in a personal knowledge management system where the true value lies in the _connections_ between notes. When a user queries a complex, multi-layered topic, standard RAG retrieves disjointed blocks of text, stripping away the structural and semantic relationships (edges) between those blocks.

**The Objective:** To engineer an autonomous retrieval agent within a local desktop environment that bridges vector-based semantic search with deterministic graph traversal. By structuring notes as a directed graph and utilizing the A* search algorithm, the system will dynamically traverse relationships to assemble a cohesive, logically sequential context window before passing it to the Large Language Model.

## 2. System Architecture

The architecture operates locally, blending an embedded database with a lightweight graph structure, connected to the frontend UI via inter-process communication (IPC).

### 2.1 The State Space (Knowledge Graph)

The foundational data structure is a directed property graph, defined as $G = (V, E)$:

- **Nodes ($V$):** Each node represents a discrete note block. Every node contains a high-dimensional embedding vector $\vec{v}$ representing its semantic meaning in the latent space.
    
- **Edges ($E$):** Edges represent explicit user-defined tags or bidirectional links between blocks (e.g., "Supports", "Contradicts", "Defines", "Follows").
    

### 2.2 The Query Optimizer

Here the agent will first pass the query through an LLM to breakdown the user's intent into more descriptive, complete and queryable input. 

### 2.3 BM25 + Dense Vector Search

This is where we use BM25 + Dense Vector Search to find 50-100 most relevant blocks.
### 2.4 ColBERT Reranking

Then we use ColBERT reranking to rerank this set of blocks in order of relevancy
### 2.5 The Agentic Router

An autonomous reasoning layer that acts as the gatekeeper for user queries. It determines the retrieval strategy:

1. **Direct Recall:** If the query is strictly factual, then it will answer the query from the retrieved blocks.
    
2. **Contextual Traversal:** If the query requires synthesis across multiple concepts, the agent selects top $k$ "entry nodes", and then triggers the A* traversal to map the relationships between them.
    

## 3. Mathematical Formulation of A* Traversal

The core engine of this project is the A* pathfinding algorithm, repurposed for semantic graph traversal. The algorithm evaluates candidate nodes using the standard function:

$$f(n) = g(n) + h(n)$$

### 3.1 The Cost Function: $g(n)$

The cost function represents the accumulated penalty of traversing from the starting node to the current candidate node $n$.

- In a spatial graph, this is physical distance. In our semantic graph, $g(n)$ is determined by **edge weights**.
    
- Stronger logical relationships (e.g., a "Defines" tag) have a _lower_ traversal cost, encouraging the algorithm to follow strong conceptual links. Weaker or generic tags have a higher cost.
    

### 3.2 The Heuristic Function: $h(n)$

The heuristic is the abstract directional guide—a number that prioritizes which path to explore next by estimating the relevance of node $n$ to the user's original query.

- To ensure the heuristic is admissible, we use the semantic distance in the latent space between the candidate node's embedding $\vec{n}$ and the user query's embedding $\vec{q}$.
    
- This is calculated using Cosine Distance:
    

$$h(n) = 1 - \frac{\vec{q} \cdot \vec{n}}{\|\vec{q}\| \|\vec{n}\|}$$

By minimizing $h(n)$, the algorithm is mathematically pulled toward nodes that are contextually relevant to the overarching question, ignoring graph branches that drift off-topic.

## 4. Technical Stack & Implementation Details

- **Frontend:** Web technologies wrapped in PyTauri for a lightweight, native desktop experience.
    
- **Backend Pipeline:** Python (handling embedding generation, the agentic reasoning loop, and LLM prompting).
    
- **Graph/Vector Storage:** NetworkX (for in-memory A* traversal and edge management) paired with a local vector store like ChromaDB or FAISS for the initial KNN matching.
    
- **Bridge:** Rust-Python IPC to handle the asynchronous communication between the UI and the heavy retrieval logic without freezing the application.
    

## 5. Development Roadmap (3-Phase Execution)

### Phase 1: State Space & Vector Baseline

- **Goal:** Establish the foundational data structures and standard RAG capabilities.
    
- **Tasks:**
    
    - Define the JSON/database schema for notes, capturing text, metadata, and linked edge IDs.
        
    - Implement the embedding pipeline to convert raw text blocks into latent vectors.
        
    - Build the baseline KNN retrieval function and test accuracy against single-hop queries.
        

### Phase 2: A* Algorithm & Heuristic Tuning

- **Goal:** Implement the graph traversal mechanics.
    
- **Tasks:**
    
    - Map the document structure into a `NetworkX` directed graph.
        
    - Assign numerical weights to different relationship tags to formalize $g(n)$.
        
    - Write the A* traversal function, implementing the Cosine Distance mathematical formula for $h(n)$.
        
    - **Testing:** Input two distantly related nodes and verify that the algorithm successfully finds the most logically sound path between them.
        

### Phase 3: Agent Logic & Application Integration

- **Goal:** Automate the workflow and connect it to the user interface.
    
- **Tasks:**
    
    - Write the agent's routing logic to classify user prompts and dynamically choose between simple KNN and deep A* traversal.
        
    - Develop a context-assembly function that chronologically or logically stitches the A* traversed nodes into a single text prompt for the final LLM synthesis.
        
    - Wire the Python backend to the PyTauri frontend, ensuring proper loading states are displayed while the agent traverses the graph.
        

---

Having this documented gives you a rigid framework to build against.

Would you like to start with Phase 2 and map out the exact Python code for the A* heuristic and cost functions, or would you prefer to sketch out the database schema for the nodes and edges first?