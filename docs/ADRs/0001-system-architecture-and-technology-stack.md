# ADR 0001: System Architecture, Multi-Agent Orchestration & Technology Stack

- **Status**: Accepted
- **Date**: 2026-11-06
- **Deciders**: BetriebsPilot AI Team
- **Technical Context**: PRD v1.0 / German Mittelstand B2B Suppliers

---

## 1. Context and Problem Statement

Small and mid-sized German B2B suppliers (*Mittelstand Großhandel & Zulieferer*) face an acute shortage of skilled commercial clerks (*Fachkräftemangel*). They process orders, returns (RMA), and invoice inquiries across heterogeneous unstructured channels:
- Unstructured PDF order forms (scanned or digital)
- Messy email bodies and quote references
- WhatsApp/SMS field messages and photos of damaged parts

These companies run on 15–25-year-old on-premise or LAN-hosted legacy ERP systems:
- **Sage 100** (SQL Read Views + XML/CSV Hotfolders)
- **proALPHA & abas** (OpenTRANS 2.1 XML Watch-Folders)
- **SAP Business One** (Service Layer REST API / DI-API)

Replacing these ERP systems costs €150k–€500k+ and causes months of operational disruption. Furthermore, German commercial and tax compliance laws (**GoBD** and EU **EN 16931** E-Invoicing mandates) strictly prohibit non-deterministic "black-box" modifications to financial documents.

---

## 2. Decision Drivers

1. **Deterministic Accuracy & GoBD Auditability**: The LLM must never hallucinate SKU codes, tax rates, or pricing. All writes to the ERP must be deterministically validated against master catalog data.
2. **Legacy ERP Hotfolder Compatibility**: Legacy ERPs ingest orders by watching a local file directory (e.g. `C:\ERP_Import\Incoming_Orders\`). A pure web browser app cannot write silently to local disk paths due to sandbox constraints.
3. **Multi-Channel & Multi-Modal Ingestion**: Support incoming PDFs, emails, WhatsApp messages, and SMS.
4. **Developer Experience & Maintainability**: Single unified codebase for data contracts, RAG schemas, orchestrator state, and UI.

---

## 3. Considered Options

* **Option A: Pure SaaS Web App + Microservices in Separate Repos**
* **Option B: Single Monorepo with Remote FastAPI Agent + Local Desktop Client (Selected)**
* **Option C: Direct ERP Database Mutation (Direct SQL Writes to Sage/SAP)**

---

## 4. Decision Outcome: Option B (Single Monorepo + Desktop Hotfolder Bridge)

### 4.1 Repository Layout: Single Monorepo
We structure the codebase as a single monorepo (`betriebspilot-ai`):
```
betriebspilot-ai/
├── docker-compose.yml          # PostgreSQL 16 + Qdrant + Ollama + Agent Server
├── .env.example                # Unified configuration template
├── docs/                       # PRD and Architecture Decision Records (ADRs)
│   └── ADRs/
├── agent-backend/              # Python 3.11 + FastAPI AI Agent Server
│   ├── pyproject.toml          # Docling, LangGraph, Qdrant, Instructor, Pydantic
│   ├── Modelfile               # Local Qwen2.5-7B/14B Ollama configuration
│   ├── data/seed_german_erp.py # Postgres & Qdrant seed script (10k German SKUs)
│   └── src/
│       ├── ingestion/          # Docling PDF parser + Instructor multichannel extractors
│       ├── rag/                # 3-Tier Cascade Hybrid Retriever (Dense + BM25)
│       ├── orchestrator/       # LangGraph cyclic multi-agent workflow
│       ├── erp_adapters/       # OpenTRANS 2.1 XML, SAP B1 JSON, ZUGFeRD 2.3
│       └── api/                # FastAPI REST & SSE streaming endpoints
└── desktop-client/             # Local Desktop App (Tauri v2 / Electron + React)
```

### 4.2 Runtime & Language Strategy
* **Backend Runtime**: **Python 3.11** managed via `.tool-versions` (`asdf`). Python 3.11 provides substantial performance improvements and full binary compatibility with Docling, PyTorch, LangGraph, and Pydantic v2.
* **Frontend Runtime**: **Node.js (v20+) / TypeScript** with React and TailwindCSS.
* **OS Bridge**: **Tauri v2** (or Electron) with native Rust/Node filesystem APIs to watch and write into local ERP hotfolders without browser download prompts.

### 4.3 Database Architecture (Polyglot Persistence)
* **PostgreSQL 16**:
  - Source of truth for transactional data: `erp_customers`, `erp_articles`, `erp_inventory` (with ATP: Available-to-Promise calculations), `erp_orders`, and `erp_customer_sku_map`.
  - Self-learning cross-reference table (`erp_customer_sku_map`) populated when clerks approve low-confidence items.
* **Qdrant Vector Database**:
  - Powers Hybrid Retrieval: Dense vector embeddings (`text-embedding-3-small` or `bge-m3`) combined with BM25 sparse vectors and payload filters (e.g. manufacturer, category).

### 4.4 3-Tier Cascade SKU Resolution Engine
To achieve $\ge 96\%$ resolution accuracy on messy German orders:
1. **Tier 1 (Deterministic Direct Mapping)**: Query `erp_customer_sku_map` using Customer ID + incoming raw customer item number.
2. **Tier 2 (Historical Context)**: Search customer's last 24-month order and quotation history (`erp_order_items`).
3. **Tier 3 (Qdrant Hybrid Search & Reranking)**: Execute dense + BM25 hybrid search over the 10k-SKU catalog, followed by cross-encoder re-ranking.

### 4.5 Orchestrator & State Management: LangGraph
We use **LangGraph** to model the Order-to-Cash workflow as a stateful, cyclic graph with human-in-the-loop checkpoints:
- **Node 1: `classify_intent`**: Identifies channel and intent (`SALES_ORDER`, `RETURN_RMA`, `INVOICE_QUERY`, `STOCK_CHECK`).
- **Node 2: `resolve_order_items`**: Runs the 3-Tier SKU cascade and deterministic packaging math (e.g. $10\text{ Kartons} \times 12 = 120\text{ Dosen}$).
- **Node 3: `check_inventory_atp`**: Verifies Available-to-Promise stock ($ATP = \text{Stock}_{phys} - \text{Stock}_{reserved} + \text{Stock}_{incoming}$).
- **Node 4: `confidence_gate`**:
  - $\text{Confidence} \ge 0.95$ and in stock $\rightarrow$ **Auto-export** (`generate_legacy_file`).
  - $\text{Confidence} < 0.95$ or out-of-stock $\rightarrow$ Pause graph and route to **Split-Screen Human Review**.

### 4.6 Legacy ERP Export Adapters
The output generation is decoupled into modular adapters:
- **OpenTRANS 2.1 XML**: Standard for Sage 100, proALPHA, and abas.
- **SAP Business One JSON**: Direct schema for SAP Service Layer REST API.
- **ZUGFeRD 2.3 / XRechnung**: EN 16931-compliant German electronic invoicing (hybrid PDF/A-3 + Factur-X XML).

---

## 5. Consequences & Compliance

### Positive
- **GoBD Auditability**: The LLM outputs structured proposals via Instructor/Pydantic; business rules and tax calculations are strictly deterministic.
- **Zero Sync Hell**: Monorepo allows sharing Pydantic schemas (exported to TypeScript types) between backend and frontend.
- **Offline / Air-Gapped Ready**: Compatible with local Ollama (`qwen2.5:7b-instruct`) for privacy-sensitive German Mittelstand clients.

### Negative / Trade-Offs
- Developers must maintain Docker Compose services (Postgres + Qdrant) locally.
- Requires building and packaging desktop binaries for Windows/macOS.
