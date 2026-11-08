# BetriebsPilot AI — Engineering Wiki & Knowledge Base

Welcome to the internal engineering wiki for **BetriebsPilot AI**. This knowledge base documents core architectural patterns, machine learning foundations, and Python engineering standards for team members and developers.

---

## 📚 Knowledge Base Index

### 🚀 Getting Started & Hands-On Playground
* **[Hands-On Guide: Playing, Testing & Debugging the Backend](getting-started/hands-on-backend-guide.md)**
  - Mental model of the autonomous back-office agent.
  - Complete code map of `agent-backend/src/` (what runs with an LLM vs. 100% deterministic Python).
  - Running FastAPI & interactive Swagger UI playground scenarios (High-confidence auto-export, Human review, 1-Click approval, Semantic vector search).
  - Pytest commands, selective testing (`-k`), stdout logging (`-s`), and debugging with `breakpoint()`.
  - Direct database and Qdrant vector exploration.

### 1. Vector Database & Hybrid RAG Architecture
* **[How Vector Search Works Under the Hood](vector-database/how-it-works.md)**
  - Foundational primer on high-dimensional vectors (384 dimensions) and embeddings.
  - Sub-word tokenization and ONNX Runtime performance optimizations.
  - HNSW graph indexing ($\mathcal{O}(\log N)$ nearest neighbor search).
  - The "Danger Zone": Why pure dense vectors confuse `M8x30` with `M8x40` and how Qdrant's BM25 hybrid search solves it.
* **[3-Tier Cascade SKU Resolution & Packaging Math](rag/three-tier-cascade.md)**
  - Tier 1: Deterministic Direct Alias Mapping (`erp_customer_sku_map`).
  - Tier 2: 24-Month Customer Order History Lookup (`erp_orders` + `erp_order_items`).
  - Tier 3: Qdrant Hybrid Semantic Search over the master ERP catalog.
  - Deterministic packaging math (converting *Kartons* & *Dosen* into base units *STK*).
  - Human-in-the-Loop confidence thresholds and self-learning alias loop.

### 2. Python Engineering & Agent Architecture
* **[Ingestion Parser: Python Engineering & Architectural Deep-Dive](ingestion/ingestion-parser-deep-dive.md)**
  - Modern Python 3.11 patterns: Type Hinting, Generics, and static safety.
  - Pydantic v2: Data contracts, runtime validation, and `@field_validator` for German decimal numbers.
  - The Instructor Pattern: Forcing LLMs into deterministic structured output with automatic validation retries.
  - Multi-channel ingestion pipeline: Hybrid PDF processing (`pypdf` + `Docling`), email sanitization, and chat normalization.
* **[LangGraph State Machine & Multi-Agent Orchestration](orchestrator/langgraph-workflow.md)**
  - Stateful cyclic workflows and why linear chains fail in German legacy ERPs.
  - `TypedDict` blackboard state architecture across graph nodes.
  - Real-time Available-to-Promise (ATP) inventory check ($\text{physical} - \text{reserved} + \text{incoming}$).
  - Multi-tier Confidence Gate and Human-in-the-Loop (HITL) autonomy guardrails.
* **[FastAPI Agent Server & Real-Time SSE Streaming](api/fastapi-server-architecture.md)**
  - Client-server bridge between remote FastAPI agent and local Tauri desktop app.
  - Multipart uploads handling both digital PDFs and raw email text uniformly.
  - Server-Sent Events (SSE) streaming live LangGraph node traces.
  - One-click approval endpoint triggering Tier 1 self-learning alias loop.

### 3. Desktop Client & Hotfolder Integration
* **[Desktop Client: Architecture & Implementation Plan](desktop-client/architecture-and-implementation-plan.md)**
  - Why legacy German ERPs require a desktop hotfolder writer (`C:\ERP_Import\` or `/tmp/erp_import`).
  - High-density 3-column cockpit design (`OmnichannelInput`, `AgentLiveTrace`, `SplitScreenReview`, `ErpExportPanel`).
  - Shared TypeScript data contracts and live Server-Sent Events (SSE) streaming.
  - 1-Click human approval and database self-learning loop.

---

## 🏛️ Related Architectural Documents

* **[ADR 0001: System Architecture, Multi-Agent Orchestration & Technology Stack](../ADRs/0001-system-architecture-and-technology-stack.md)**
* **[ADR 0002: Vector Database Selection (Qdrant) for Semantic Catalog Retrieval](../ADRs/0002-vector-database-selection-qdrant.md)**
* **[Product Requirements Document (PRD v1.0)](../BetriebsPilot_AI_ERP_Agent_PRD.pdf)**
