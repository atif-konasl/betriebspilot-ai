"""
Unit and integration tests for the FastAPI Agent Server endpoints.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ingestion.schemas import RawExtractedDocument, CustomerReference, ExtractedLineItem, InputChannel


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ------------------------------------------------------------------------------
# 1. System & Health Endpoints
# ------------------------------------------------------------------------------
def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["database"]["connected"] is True
    assert data["qdrant"]["connected"] is True


def test_list_customers_endpoint(client):
    res = client.get("/api/v1/customers")
    assert res.status_code == 200
    customers = res.json()
    assert len(customers) == 10
    assert any(c["customer_id"] == "DE-10021" for c in customers)


# ------------------------------------------------------------------------------
# 2. Swagger & OpenAPI Documentation
# ------------------------------------------------------------------------------
def test_swagger_documentation(client):
    # OpenAPI JSON specification
    res = client.get("/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert "BetriebsPilot AI" in spec["info"]["title"]
    assert "/api/v1/process-input" in spec["paths"]
    assert "/api/v1/approve-and-export" in spec["paths"]
    assert "/api/v1/erp-catalog/search" in spec["paths"]

    # Swagger UI HTML
    docs_res = client.get("/docs")
    assert docs_res.status_code == 200
    assert "swagger-ui" in docs_res.text.lower()


# ------------------------------------------------------------------------------
# 3. Catalog Vector Search Endpoint
# ------------------------------------------------------------------------------
def test_catalog_vector_search(client):
    res = client.get("/api/v1/erp-catalog/search?query=Sechskantschraube+M8&limit=3")
    assert res.status_code == 200
    results = res.json()
    assert len(results) > 0
    assert results[0]["score"] > 0.60
    assert "sku" in results[0]
    assert "title_de" in results[0]


# ------------------------------------------------------------------------------
# 4. Processing Endpoint (POST /api/v1/process-input)
# ------------------------------------------------------------------------------
def test_process_input_missing_parameters_rejected(client):
    res = client.post("/api/v1/process-input", data={"channel": "email"})
    assert res.status_code == 400
    assert "either a pdf file upload or non-empty raw_text" in res.json()["detail"].lower()


@patch("src.orchestrator.nodes.MultiChannelParser")
def test_process_input_raw_text_success(mock_parser_cls, client):
    mock_parser = MagicMock()
    mock_parser.parse.return_value = RawExtractedDocument(
        channel=InputChannel.EMAIL,
        customer=CustomerReference(company_name="Müller Maschinenbau GmbH & Co. KG"),
        customer_order_number="PO-TEST-100",
        line_items=[
            ExtractedLineItem(
                line_number=1,
                raw_description="O-Ring",
                raw_item_number="MM-O-687",
                quantity=2,
                raw_uom="Dosen"
            )
        ]
    )
    mock_parser_cls.return_value = mock_parser

    res = client.post(
        "/api/v1/process-input",
        data={
            "raw_text": "Bestellung: 2 Dosen MM-O-687",
            "channel": "email",
            "customer_id": "DE-10021",
            "export_format": "opentrans_xml"
        }
    )

    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == "DE-10021"
    assert len(data["resolved_items"]) == 1
    assert data["resolved_items"][0]["matched_sku"] == "ART-O-RING-22X3_0-BRAUN-1087"
    assert "classify_intent" in data["execution_trace"]


# ------------------------------------------------------------------------------
# 5. Approval & Legacy Export Endpoint (POST /api/v1/approve-and-export)
# ------------------------------------------------------------------------------
def test_approve_and_export_opentrans(client):
    payload = {
        "task_id": "task-test-approval-1",
        "customer_id": "DE-10021",
        "customer_order_number": "PO-APPROVED-99",
        "order_date": "2026-11-07",
        "delivery_date": "2026-11-14",
        "export_format": "opentrans_xml",
        "learn_aliases": True,
        "approved_line_items": [
            {
                "line_number": 1,
                "raw_item_number": "MM-CUSTOM-NEW-01",
                "matched_sku": "ART-DIN-M8X30-88-1010",
                "title_de": "Sechskantschraube DIN 933 M8x30",
                "base_quantity": 500.0,
                "base_uom": "STK",
                "unit_price_net": 0.18,
                "total_price_net": 90.0,
                "tax_rate": 19.0
            }
        ]
    }

    res = client.post("/api/v1/approve-and-export", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["task_id"] == "task-test-approval-1"
    assert data["learned_alias_count"] == 1
    assert data["file_name"].endswith(".xml")
    assert "<ORDER" in data["payload_content"]
    assert "PO-APPROVED-99" in data["payload_content"]


def test_approve_and_export_sap_b1(client):
    payload = {
        "task_id": "task-test-sap-1",
        "customer_id": "DE-10021",
        "customer_order_number": "PO-SAP-77",
        "export_format": "sap_b1_json",
        "learn_aliases": False,
        "approved_line_items": [
            {
                "line_number": 1,
                "matched_sku": "ART-DIN-M8X30-88-1010",
                "title_de": "Sechskantschraube DIN 933 M8x30",
                "base_quantity": 250.0,
                "base_uom": "STK",
                "unit_price_net": 0.20,
                "total_price_net": 50.0,
                "tax_rate": 19.0
            }
        ]
    }

    res = client.post("/api/v1/approve-and-export", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["file_name"].endswith(".json")
    assert '"CardCode": "DE-10021"' in data["payload_content"]


# ------------------------------------------------------------------------------
# 6. Server-Sent Events (SSE) Stream Trace
# ------------------------------------------------------------------------------
def test_stream_trace_endpoint(client):
    res = client.get("/api/v1/stream-trace/test-task-uuid-123")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert "classify_intent" in res.text
    assert "confidence_gate" in res.text
