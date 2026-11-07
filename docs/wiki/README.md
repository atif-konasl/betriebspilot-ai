# BetriebsPilot AI — Engineering Wiki & Knowledge Base

Welcome to the internal engineering wiki for **BetriebsPilot AI**. This knowledge base documents core architectural patterns, machine learning foundations, and Python engineering standards for team members and developers.

---

## 📚 Knowledge Base Index

### 1. Vector Database & Hybrid RAG Architecture
* **[How Vector Search Works Under the Hood](vector-database/how-it-works.md)**
  - Foundational primer on high-dimensional vectors (384 dimensions) and embeddings.
  - Sub-word tokenization and ONNX Runtime performance optimizations.
  - HNSW graph indexing ($\mathcal{O}(\log N)$ nearest neighbor search).
  - The "Danger Zone": Why pure dense vectors confuse `M8x30` with `M8x40` and how Qdrant's BM25 hybrid search solves it.

### 2. Python Engineering & Agent Architecture
* **[Ingestion Parser: Python Engineering & Architectural Deep-Dive](python/ingestion-parser-deep-dive.md)**
  - Modern Python 3.11 patterns: Type Hinting, Generics, and static safety.
  - Pydantic v2: Data contracts, runtime validation, and `@field_validator` for German decimal numbers.
  - The Instructor Pattern: Forcing LLMs into deterministic structured output with automatic validation retries.
  - Multi-channel ingestion pipeline: Hybrid PDF processing (`pypdf` + `Docling`), email sanitization, and chat normalization.

---

## 🏛️ Related Architectural Documents

* **[ADR 0001: System Architecture, Multi-Agent Orchestration & Technology Stack](../ADRs/0001-system-architecture-and-technology-stack.md)**
* **[ADR 0002: Vector Database Selection (Qdrant) for Semantic Catalog Retrieval](../ADRs/0002-vector-database-selection-qdrant.md)**
* **[Product Requirements Document (PRD v1.0)](../BetriebsPilot_AI_ERP_Agent_PRD.pdf)**
