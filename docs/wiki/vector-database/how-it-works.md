# How Vector Search Works Under the Hood

> **BetriebsPilot AI Wiki** • Vector Database Architecture • Engineering Deep-Dive  
> **Topic**: Embedding Pipelines, Transformer Tokenization, HNSW Indexing & Hybrid Search

---

To truly master RAG as an AI Engineer, understanding what happens inside `embedder.embed(texts)`—and why a Vector Database is needed once a catalog grows from 3 sample items to 50,000+ German ERP items—is one of the most critical concepts in modern agent engineering.

This document breaks down the end-to-end mathematical and engineering pipeline **under the hood**.

---

## Part 1: Why Did "Sechskantschraube" Match "Schraube mit 6-Kant Kopf"?

In a traditional relational SQL database (such as PostgreSQL, SAP Business One, or Sage 100), querying with string pattern matching:

```sql
SELECT * FROM erp_articles WHERE title_de LIKE '%Sechskantschraube%';
```

compares **raw characters**. Because `"Schraube mit 6-Kant Kopf"` shares no exact character substring with `"Sechskantschraube"`, SQL returns **0 rows**.

An **Embedding Model** (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) does not compare characters. It translates text into a **384-dimensional mathematical coordinate** where each dimension represents a learned semantic concept (e.g., *fastener/metal, hexagonal drive, metric thread size, elastomer/seal*). Because the neural network was pre-trained on millions of multilingual sentences, it has learned that *"Sechskant"* and *"6-Kant Kopf"* occupy the exact same neighborhood in geometric space.

---

## Part 2: How FastEmbed Works Internally (The 5-Step Pipeline)

When you execute:
```python
vectors = list(embedder.embed(texts))
```

**FastEmbed** (developed by the Qdrant team) executes a 5-stage pipeline optimized directly for the CPU using C++ SIMD instructions:

```
"Schraube mit 6-Kant Kopf M8 30mm"
       │
       ▼  1. Rust Tokenizer (WordPiece / Sub-words)
[101, 28412, 1029, 126, 118, 19402, 14099, 181, 240, 1091, 2619, 102]
       │
       ▼  2. ONNX Runtime C++ Graph (12 Transformer Layers + Self-Attention)
Token Vectors: 12 tokens × 384 dimensions (Matrix Shape: [12, 384])
       │
       ▼  3. Mean Pooling (Attention-Mask Weighted Average across tokens)
Single Raw Sentence Vector: 1 × 384 numbers (Shape: [384])
       │
       ▼  4. L2 Normalization (Scales vector Euclidean length to exactly 1.0)
[0.0412, -0.0891, 0.0124, ..., 0.0631]  (384 float32 numbers, norm = 1.0)
```

---

### Step 1: Download & ONNX Quantization (`TextEmbedding(...)`)

* **The Problem with Standard PyTorch**: Standard Hugging Face `sentence-transformers` loads a heavy PyTorch model (`model.bin`), which consumes significant RAM and initializes slowly on CPU.
* **The FastEmbed Solution**: FastEmbed downloads an **ONNX (Open Neural Network Exchange)** quantized version of the model. ONNX compiles the neural network into a static C++ computation graph optimized for CPU vector instructions (AVX2 / AVX-512 on Intel/AMD or NEON on Apple Silicon), making inference **2x to 4x faster** with a fraction of the memory footprint.

---

### Step 2: Sub-Word Tokenization (Why German Compound Words Work!)

German is famous for complex compound words like *Sechskantschraube* or *Wellendichtring*.

Inside FastEmbed, Hugging Face's high-performance **Rust tokenizers** library splits compound words into **sub-word tokens** and maps them to vocabulary integer IDs:

* `"Sechskantschraube"` $\rightarrow$ `["Sechs", "##kant", "##schraube"]`
* `"Schraube mit 6-Kant"` $\rightarrow$ `["Schraube", "mit", "6", "-", "Kant"]`

Notice that both sentences share the common sub-word stems `"kant"` and `"schraube"`. The tokenizer also pads the batch to a uniform length and generates an `attention_mask` ($1$ for meaningful tokens, $0$ for padding).

---

### Step 3: Forward Pass Through the 12-Layer Transformer

1. The token IDs enter the **12 Transformer Self-Attention layers**.
2. **Self-Attention** allows every token to examine its neighboring words to disambiguate context:
   - For example, the token `"M8"` looks at `"Schraube"` and understands that `"M8"` designates an *8mm metric thread* (rather than a BMW M8 vehicle or an M8 motorway).
3. **Layer Output**: Rather than emitting a single vector for the entire sentence, the Transformer outputs **one 384-dimensional vector per token** (e.g., 12 tokens $\rightarrow$ a $12 \times 384$ matrix).

---

### Step 4: Mean Pooling (Collapsing Tokens into 1 Sentence Vector)

To collapse the $12 \times 384$ matrix into a single 384-number vector representing the overall product description, FastEmbed applies **Mean Pooling**:

$$\vec{v}_{\text{raw}} = \frac{\sum_{i=1}^{N} m_i \cdot \vec{t}_i}{\sum_{i=1}^{N} m_i}$$

Where $m_i \in \{0, 1\}$ is the attention mask (ignoring zero-padding) and $\vec{t}_i$ is the token vector. The result is a single array of 384 `float32` numbers.

---

### Step 5: L2 Normalization (The Cosine Similarity Shortcut)

Finally, the vector is normalized by its Euclidean length ($\|\vec{v}\|_2$):

$$\vec{v}_{\text{norm}} = \frac{\vec{v}_{\text{raw}}}{\|\vec{v}_{\text{raw}}\|_2}$$

$$\text{where } \|\vec{v}_{\text{raw}}\|_2 = \sqrt{\sum_{k=1}^{384} v_k^2}$$

#### Why Normalization Matters for Performance:
The standard Cosine Similarity formula is:

$$\text{Cosine Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \cdot \|\vec{v}\|_2}$$

When vectors are L2-normalized so that $\|\vec{u}\|_2 = 1.0$ and $\|\vec{v}\|_2 = 1.0$, the denominator becomes $1.0 \times 1.0 = 1.0$.

$$\text{Cosine Similarity}(\vec{u}_{\text{norm}}, \vec{v}_{\text{norm}}) = \vec{u}_{\text{norm}} \cdot \vec{v}_{\text{norm}}$$

This simplifies the calculation to a **single dot product**, saving millions of square root calculations per second!

---

## Part 3: What Does a Vector Database (Qdrant) Actually Do?

In a small Python script, comparing 1 query vector against 3 catalog items using `np.dot()` takes microseconds.

### The Scaling Problem in Production ERPs
In a real German Mittelstand distributor with **100,000 SKUs**, if 20 clerks process 50-line order attachments concurrently:

$$100{,}000 \text{ SKUs} \times 50 \text{ lines} \times 20 \text{ orders} = 100{,}000{,}000 \text{ dot products}$$

A brute-force Python loop will max out CPU cores, freeze the server, and lose all in-memory vectors upon script restart.

**Qdrant** solves this with three core architectural innovations:

---

### 1. HNSW Graph Indexing: $\mathcal{O}(\log N)$ Search Instead of $\mathcal{O}(N)$

Instead of checking 100,000 vectors sequentially, Qdrant builds an **HNSW (Hierarchical Navigable Small World)** graph—comparable to a multi-level highway network:

```
Layer 2 (Autobahn)     : [Fasteners] ───────────────► [Seals] ───────────────► [Bearings]
                              │                          │
Layer 1 (Landstraße)   : [Hex Bolts] ──► [Cap Screws]   [O-Rings] ──► [Gaskets]
                              │
Layer 0 (Local Street) : [DIN 933 M8x30] ──► [DIN 933 M8x40] ──► [DIN 933 M10x30]
```

* **Top Layer**: Traverses coarse cluster hubs (Fasteners vs. Seals vs. Bearings).
* **Middle Layer**: Zooms into product sub-categories (Hex Bolts vs. Socket Screws).
* **Bottom Layer**: Pinpoints the exact item (`DIN 933 M8x30`) and its immediate nearest neighbors.
* **Performance**: Searching 100,000 SKUs requires calculating **~150 distance hops** instead of 100,000 comparisons, completing in **< 2 milliseconds**.

---

### 2. Payload Filtering (In-Graph Pre-Filtering)

In legacy ERPs, orders often carry business constraints:
> *"Find the closest match to 'O-Ring 22mm', **BUT ONLY** where `warehouse == 'WH-CENTRAL'` and `in_stock >= 50`."*

Traditional databases must either:
1. Filter first in SQL, then search vectors (slow and drops relevant items), or
2. Search vectors first, then filter (often returns 0 items if top matches are out of stock).

Qdrant links payload metadata directly to an inverted index **inside the HNSW graph**, filtering nodes on-the-fly during graph traversal with zero performance loss.

---

### 3. The "Danger Zone": Why Pure Dense Vectors Need Sparse BM25

Consider this classic industrial failure case:

* **ERP SKU 1**: `"DIN 933 Sechskantschraube M8x30 verzinkt"`
* **ERP SKU 2**: `"DIN 933 Sechskantschraube M8x40 verzinkt"`
* **Customer Text**: `"Schraube mit 6-Kant Kopf M8 30mm"`

Because both SKUs are zinc-plated hex bolts that share 95% of the same semantic meaning, a pure dense embedding model produces almost identical similarity scores:
* Match with M8x30: **0.775**
* Match with M8x40: **0.776** ⚠️ (*Tie or slight misclassification!*)

#### The Solution: Hybrid Search with Reciprocal Rank Fusion (RRF)
To prevent delivering the wrong screw length to a German factory, Qdrant combines two search paradigms:

1. **Dense Vector (384 floats)**: Captures **semantic meaning & synonyms** (*"6-Kant"* == *"Sechskant"*).
2. **Sparse BM25 Vector**: Captures **exact lexical tokens & dimensions** (*"30"* vs. *"40"*).
3. **Reciprocal Rank Fusion (RRF)**: Merges the rank positions of both searches:

$$RRF\_Score(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{60 + \text{rank}_m(d)}$$

Because `"30"` exactly matches the BM25 token for `M8x30` but has zero overlap with `M8x40`, the hybrid score decisively ranks **M8x30 as #1**.

---

## Part 4: Runnable Python Inspection Script

Run this script inside `agent-backend` to verify vector shapes, normalization, and similarity scoring live on your machine:

```python
import numpy as np
from fastembed import TextEmbedding

# 1. Initialize Multilingual 384-dimensional model
embedder = TextEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

texts = [
    "DIN 933 Sechskantschraube M8x30 verzinkt",  # [0] ERP SKU 1 (30mm)
    "DIN 933 Sechskantschraube M8x40 verzinkt",  # [1] ERP SKU 2 (40mm - Danger Zone)
    "Schraube mit 6-Kant Kopf M8 30mm",          # [2] Incoming customer order
    "O-Ring Gummidichtung 22mm schwarz"          # [3] Completely unrelated seal
]

# 2. Generate embeddings
raw_vectors = list(embedder.embed(texts))

# 3. L2-Normalize vectors to unit length (norm = 1.0)
vectors = [v / np.linalg.norm(v) for v in raw_vectors]

print(f"Vector Dimensions   : {vectors[0].shape[0]} (Type: {vectors[0].dtype})")
print(f"L2 Norm (Length)    : {np.linalg.norm(vectors[0]):.4f}")
print(f"First 5 Dimensions  : {np.round(vectors[0][:5], 4)}\n")

# 4. Compute Cosine Similarities via Dot Product
sim_m8x30 = np.dot(vectors[2], vectors[0])
sim_m8x40 = np.dot(vectors[2], vectors[1])
sim_oring = np.dot(vectors[2], vectors[3])

print(f"Query vs M8x30 (Target SKU)   : {sim_m8x30:.4f}")
print(f"Query vs M8x40 (Wrong Length) : {sim_m8x40:.4f}  <-- Pure dense tie!")
print(f"Query vs O-Ring (Unrelated)   : {sim_oring:.4f}")
```

### Expected Output:
```text
Vector Dimensions   : 384 (Type: float32)
L2 Norm (Length)    : 1.0000
First 5 Dimensions  : [-0.0255  0.0524 -0.0209 -0.0336 -0.0534]

Query vs M8x30 (Target SKU)   : 0.7753
Query vs M8x40 (Wrong Length) : 0.7761  <-- Pure dense tie!
Query vs O-Ring (Unrelated)   : 0.5931
```

---

## Summary: Key Takeaways for BetriebsPilot AI

| Concept | What It Is | Why It Matters in Our Architecture |
|:---|:---|:---|
| **Sub-word Tokenizer** | Splits compound German words into morpheme roots | Allows matching *"Sechskantschraube"* with *"6-Kant"* without manual dictionaries. |
| **ONNX Runtime** | Quantized C++ execution engine | Replaces PyTorch with 3x faster CPU execution and minimal RAM usage. |
| **L2 Normalization** | Scales vector lengths to $1.0$ | Enables calculating Cosine Similarity using a single vector dot product. |
| **HNSW Graph** | Hierarchical Navigable Small World search graph | Enables Qdrant to search 100,000+ SKUs in $< 2\text{ms}$ with $\mathcal{O}(\log N)$ complexity. |
| **Dense + Sparse Hybrid** | Combines 384D conceptual vectors with BM25 tokens | Eliminates dimension misclassifications (e.g., `M8x30` vs. `M8x40`). |
