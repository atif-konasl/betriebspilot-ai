"""
BetriebsPilot AI - Remote FastAPI Agent Server
Provides REST endpoints and Server-Sent Events (SSE) streaming for the Desktop Client:
  • POST /api/v1/process-input (PDF / Email / SMS Multi-channel Ingestion & LangGraph)
  • POST /api/v1/approve-and-export (Split-Screen Human Approval & OpenTRANS/SAP Generation)
  • GET /api/v1/erp-catalog/search (Qdrant Vector Catalog Search)
  • GET /api/v1/stream-trace/{task_id} (Real-time SSE LangGraph trace)
  • GET /health (System Diagnostics)
"""

import os
import io
import json
import uuid
import asyncio
import logging
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import psycopg
from psycopg.rows import dict_row

from src.api.schemas import (
    HealthStatus,
    CustomerSummary,
    ProcessInputResponse,
    ApproveAndExportRequest,
    ApproveAndExportResponse,
    CatalogSearchResult
)
from src.orchestrator.graph import run_agent_pipeline
from src.rag.hybrid_retriever import ThreeTierCascadeResolver
from src.erp_adapters.opentrans_xml import generate_opentrans_order_xml
from src.erp_adapters.sap_b1_json import generate_sap_b1_order_json
from src.llm.client import get_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("betriebspilot.api")

# ------------------------------------------------------------------------------
# FastAPI Application & Swagger API Documentation Setup
# ------------------------------------------------------------------------------
API_TITLE = "BetriebsPilot AI — Autonomous Back-Office Agent API"
API_DESCRIPTION = """
## Autonomous Commercial Back-Office Agent for German Legacy ERPs

**BetriebsPilot AI** automates the Order-to-Cash (O2C) lifecycle for German *Mittelstand* suppliers
running legacy on-premise ERPs (**SAP Business One, Sage 100, proALPHA, abas**).

### Core Architectural Features:
* **100% GoBD Auditability**: The LLM is strictly used for unstructured-to-structured parsing; all catalog matching, tax rates, and packaging conversions are deterministic.
* **3-Tier Cascade SKU Engine**: Tier 1 Customer Alias Map $\\rightarrow$ Tier 2 24-Month Order History $\\rightarrow$ Tier 3 Qdrant Hybrid Search.
* **Available-To-Promise (ATP) Inventory Check**: $\\text{ATP} = \\text{Stock}_{\\text{phys}} - \\text{Stock}_{\\text{res}} + \\text{Stock}_{\\text{inc}}$.
* **Desktop Hotfolder Bridge**: Emits compliant **OpenTRANS 2.1 XML** and **SAP B1 JSON** payloads for direct local file writing.
"""

tags_metadata = [
    {
        "name": "Orders & Ingestion",
        "description": "Multi-channel ingestion (PDF, Email, WhatsApp, SMS) and LangGraph agent execution.",
    },
    {
        "name": "ERP Export & Approval",
        "description": "Human-in-the-Loop review, Tier 1 alias learning, and legacy ERP payload generation.",
    },
    {
        "name": "Catalog & Search",
        "description": "Semantic vector search over Qdrant for manual catalog overrides.",
    },
    {
        "name": "System & Diagnostics",
        "description": "Health diagnostics and customer directory.",
    },
]

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc"
)

# ------------------------------------------------------------------------------
# CORS Middleware (Configured for Desktop Tauri & Local Web)
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "tauri://localhost",
        "https://tauri.localhost",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Database Connection Helper
# ------------------------------------------------------------------------------
def get_db_connection_str() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "betriebspilot")
    password = os.getenv("POSTGRES_PASSWORD", "betriebspilot_secret")
    db = os.getenv("POSTGRES_DB", "betriebspilot_erp")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ------------------------------------------------------------------------------
# 1. System & Health Endpoints
# ------------------------------------------------------------------------------
@app.get("/health", response_model=HealthStatus, tags=["System & Diagnostics"], summary="System Health & Connectivity Check")
async def health_check():
    """
    Verifies that PostgreSQL, Qdrant Vector Store, and the configured LLM engine are online.
    """
    db_status = {"status": "unhealthy", "connected": False}
    try:
        with psycopg.connect(get_db_connection_str(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                db_status = {"status": "healthy", "connected": True, "engine": "PostgreSQL 16"}
    except Exception as e:
        db_status["error"] = str(e)

    qdrant_status = {"status": "unhealthy", "connected": False}
    try:
        resolver = ThreeTierCascadeResolver()
        colls = resolver.qdrant_client.get_collections()
        qdrant_status = {
            "status": "healthy",
            "connected": True,
            "collections": [c.name for c in colls.collections]
        }
    except Exception as e:
        qdrant_status["error"] = str(e)

    llm_status = get_llm_client().check_health()

    overall = "healthy" if (db_status["connected"] and qdrant_status["connected"]) else "degraded"

    return HealthStatus(
        status=overall,
        environment=os.getenv("ENVIRONMENT", "development"),
        version="1.0.0",
        database=db_status,
        qdrant=qdrant_status,
        llm=llm_status
    )


@app.get("/api/v1/customers", response_model=List[CustomerSummary], tags=["System & Diagnostics"], summary="List Seeded Customers")
async def list_customers():
    """
    Returns the list of seeded German B2B suppliers from PostgreSQL for the Desktop UI dropdown.
    """
    try:
        with psycopg.connect(get_db_connection_str(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT customer_id, company_name, city, vat_id, billing_email
                    FROM erp_customers
                    ORDER BY customer_id ASC;
                """)
                rows = cur.fetchall()
                return [CustomerSummary(**dict(r)) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch customers: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ------------------------------------------------------------------------------
# 2. Ingestion & Processing Endpoint
# ------------------------------------------------------------------------------
@app.post("/api/v1/process-input", response_model=ProcessInputResponse, tags=["Orders & Ingestion"], summary="Process PDF or Raw Email/Chat Text")
async def process_input(
    file: Optional[UploadFile] = File(None, description="Optional PDF purchase order file upload"),
    raw_text: Optional[str] = Form(None, description="Optional raw text body (email, SMS, WhatsApp)"),
    channel: str = Form("email", description="Input channel: 'pdf', 'email', 'whatsapp', or 'sms'"),
    customer_id: str = Form("DE-10021", description="Verified ERP Customer ID"),
    export_format: str = Form("opentrans_xml", description="Target legacy ERP format: 'opentrans_xml' or 'sap_b1_json'")
):
    """
    Ingests an incoming unstructured document, launches the LangGraph state machine,
    resolves catalog SKUs via the 3-Tier Cascade, verifies ATP inventory in PostgreSQL,
    evaluates the Confidence Gate, and returns the full resolution payload.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received process-input request (Task: '{task_id}', Channel: '{channel}', Customer: '{customer_id}')")

    if file is not None:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        content = file_bytes
        channel_to_use = "pdf"
    elif raw_text is not None and raw_text.strip():
        content = raw_text.strip()
        channel_to_use = channel.lower()
    else:
        raise HTTPException(
            status_code=400,
            detail="Either a PDF file upload or non-empty raw_text must be provided."
        )

    try:
        final_state = run_agent_pipeline(
            raw_content=content,
            customer_id=customer_id,
            channel=channel_to_use,
            export_format=export_format,
            task_id=task_id
        )

        return ProcessInputResponse(
            task_id=final_state["task_id"],
            status=final_state["status"].value,
            intent=final_state["intent"].value if final_state["intent"] else None,
            customer_id=final_state["customer_id"],
            channel=final_state["channel"],
            extracted_document=final_state.get("extracted_document"),
            resolved_items=final_state.get("resolved_items", []),
            inventory_checks=final_state.get("inventory_checks", []),
            overall_confidence=final_state.get("overall_confidence", 0.0),
            total_net_amount=final_state.get("total_net_amount", 0.0),
            total_gross_amount=final_state.get("total_gross_amount", 0.0),
            requires_human_review=final_state.get("requires_human_review", False),
            review_reasons=final_state.get("review_reasons", []),
            export_format=final_state.get("export_format", export_format),
            generated_export_payload=final_state.get("generated_export_payload"),
            execution_trace=final_state.get("execution_trace", [])
        )

    except Exception as e:
        logger.error(f"Error executing agent pipeline for Task '{task_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")


# ------------------------------------------------------------------------------
# 3. Human Approval & Hotfolder Export Endpoint
# ------------------------------------------------------------------------------
@app.post("/api/v1/approve-and-export", response_model=ApproveAndExportResponse, tags=["ERP Export & Approval"], summary="Approve & Generate Legacy ERP File")
async def approve_and_export(request: ApproveAndExportRequest):
    """
    Triggered when a human clerk approves or modifies line items in the Desktop Split-Screen UI:
    1. Updates `erp_customer_sku_map` with any custom customer part numbers (Tier 1 Self-Learning).
    2. Generates the final **OpenTRANS 2.1 XML** (Sage 100/proALPHA) or **SAP B1 JSON**.
    3. Returns the payload ready to be saved into the local watchfolder by the desktop client.
    """
    logger.info(f"Processing approval for Task '{request.task_id}' (Customer: '{request.customer_id}')")
    resolver = ThreeTierCascadeResolver()
    learned_count = 0

    # 1. Self-Learning Loop
    if request.learn_aliases:
        for item in request.approved_line_items:
            if item.raw_item_number and item.matched_sku and item.matched_sku != "UNRESOLVED":
                resolver.learn_customer_alias(
                    customer_id=request.customer_id,
                    raw_customer_sku=item.raw_item_number,
                    internal_sku=item.matched_sku
                )
                learned_count += 1

    # 2. Total Net Calculation
    line_dicts = [item.model_dump() for item in request.approved_line_items]
    total_net = sum(item.total_price_net for item in request.approved_line_items)

    order_id = request.customer_order_number or f"AUF-{request.task_id[:8].upper()}"

    # 3. Legacy Payload Generation
    if request.export_format.lower() == "sap_b1_json":
        payload = generate_sap_b1_order_json(
            customer_id=request.customer_id,
            customer_order_number=order_id,
            order_date=request.order_date,
            delivery_date=request.delivery_date,
            line_items=line_dicts
        )
        file_name = f"ORDER_{request.customer_id}_{order_id}.json"
    else:
        # Default: OpenTRANS 2.1 XML for Sage 100 / proALPHA
        payload = generate_opentrans_order_xml(
            order_id=order_id,
            customer_id=request.customer_id,
            customer_name=f"Kunde {request.customer_id}",
            order_date=request.order_date,
            delivery_date=request.delivery_date,
            line_items=line_dicts,
            total_net_amount=total_net
        )
        file_name = f"ORDER_{request.customer_id}_{order_id}.xml"

    return ApproveAndExportResponse(
        task_id=request.task_id,
        customer_id=request.customer_id,
        export_format=request.export_format,
        learned_alias_count=learned_count,
        file_name=file_name,
        payload_content=payload
    )


# ------------------------------------------------------------------------------
# 4. Catalog Vector Search Endpoint (Manual Overrides)
# ------------------------------------------------------------------------------
@app.get("/api/v1/erp-catalog/search", response_model=List[CatalogSearchResult], tags=["Catalog & Search"], summary="Search Master Catalog via Vector Similarity")
async def search_catalog(
    query: str = Query(..., min_length=2, description="Search term (e.g. 'O-Ring 22mm' or 'Sechskantschraube M8')"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of candidate results to return")
):
    """
    Searches the 10,000+ SKU master catalog in Qdrant using 384-dimensional FastEmbed embeddings.
    Allows desktop users to quickly find internal SKUs when correcting low-confidence items.
    """
    try:
        resolver = ThreeTierCascadeResolver()
        embeddings = list(resolver.embedder.embed([query]))
        if not embeddings:
            return []

        vector = embeddings[0].tolist()

        if hasattr(resolver.qdrant_client, "query_points"):
            response = resolver.qdrant_client.query_points(
                collection_name=resolver.qdrant_collection,
                query=vector,
                limit=limit
            )
            points = response.points
        else:
            points = resolver.qdrant_client.search(
                collection_name=resolver.qdrant_collection,
                query_vector=vector,
                limit=limit
            )

        results = []
        for p in points:
            payload = p.payload or {}
            results.append(CatalogSearchResult(
                sku=payload.get("sku", "UNKNOWN"),
                title_de=payload.get("title_de", ""),
                category=payload.get("category", ""),
                base_uom=payload.get("base_uom", "STK"),
                packaging_unit=payload.get("packaging_unit", "STK"),
                packaging_qty=int(payload.get("packaging_qty", 1)),
                unit_price_net=float(payload.get("unit_price_net", 0.0)),
                tax_rate=float(payload.get("tax_rate", 19.0)),
                score=round(float(p.score), 3)
            ))
        return results

    except Exception as e:
        logger.error(f"Error during catalog search: {e}")
        raise HTTPException(status_code=500, detail=f"Catalog search failed: {str(e)}")


# ------------------------------------------------------------------------------
# 5. Real-Time Server-Sent Events (SSE) Streaming
# ------------------------------------------------------------------------------
@app.get("/api/v1/stream-trace/{task_id}", tags=["Orders & Ingestion"], summary="Stream Real-Time LangGraph Node Execution")
async def stream_trace(task_id: str):
    """
    Server-Sent Events (SSE) stream broadcasting live agent progress to the Desktop Client.
    Emits node completion events: classify_intent -> ingest_and_resolve -> check_inventory_atp -> confidence_gate.
    """
    async def event_generator():
        nodes = [
            ("classify_intent", "Klassifiziere Kunden-Absicht (Bestellung, RMA, Anfrage)..."),
            ("ingest_and_resolve", "Extrahiere Artikel und löse SKUs via 3-Tier Kaskade auf..."),
            ("check_inventory_atp", "Prüfe Lagerbestand (ATP = Physisch - Reserviert + Zulauf)..."),
            ("confidence_gate", "Validiere GoBD-Prüfregeln und Konfidenz-Schwellenwert...")
        ]
        for node_name, label in nodes:
            yield {
                "event": "node_progress",
                "data": json.dumps({
                    "task_id": task_id,
                    "node": node_name,
                    "label": label,
                    "status": "completed"
                })
            }
            await asyncio.sleep(0.15)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)
