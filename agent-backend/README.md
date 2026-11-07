# BetriebsPilot AI — Remote Backend Agent

> **Autonomous Back-Office Agent Server for German Legacy ERPs**  
> Built with FastAPI, LangGraph, PostgreSQL 16, Qdrant Hybrid Search, and Instructor.

---

## ⚡ Quickstart

### 1. Start Infrastructure (PostgreSQL & Qdrant)
From the project root:
```bash
docker compose up -d
```

### 2. Activate Python Virtual Environment
```bash
# In Bash/Zsh:
source .venv/bin/activate

# In Fish:
source .venv/bin/activate.fish
```

### 3. Run the Development Server
```bash
PYTHONPATH=. uvicorn src.api.server:app --reload --port 8000
```
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Testing

We have 41 automated tests verifying all layers of the system:

```bash
# Run all tests
PYTHONPATH=. pytest tests/ -v

# Run only API Server tests
PYTHONPATH=. pytest tests/test_api_server.py -v

# Run only RAG resolution & packaging math tests
PYTHONPATH=. pytest tests/test_hybrid_retriever.py -v

# Run with print output enabled (-s)
PYTHONPATH=. pytest tests/test_hybrid_retriever.py -k test_resolve_document_end_to_end -s
```

---

## 🎮 Hands-on Interactive CLI Demo

Run the end-to-end resolution pipeline directly in your terminal:
```bash
PYTHONPATH=. python evals/demo_end_to_end_resolution.py
```
This tests parsing, Tier 1, Tier 2, Tier 3 resolution, packaging math (e.g. *10 Kartons = 1,000 STK*), and ATP inventory checks.

---

## 📖 Deep-Dive Documentation

For step-by-step guides, Swagger walkthroughs, and debugging instructions:
- **[Hands-On Backend Guide](../docs/wiki/getting-started/hands-on-backend-guide.md)**
- **[FastAPI Architecture & SSE Streaming](../docs/wiki/api/fastapi-server-architecture.md)**
- **[3-Tier Cascade SKU Resolution & Packaging Math](../docs/wiki/rag/three-tier-cascade.md)**
- **[LangGraph Multi-Agent Orchestrator](../docs/wiki/orchestrator/langgraph-workflow.md)**
- **[How Vector Search Works Under the Hood](../docs/wiki/vector-database/how-it-works.md)**
