"""
Unit and integration tests for the LangGraph Orchestrator and ERP Export Adapters.
"""

from unittest.mock import patch, MagicMock
import pytest

from src.orchestrator.state import AgentState, IntentType, WorkflowStatus
from src.orchestrator.nodes import (
    classify_intent_node,
    confidence_gate_node,
    check_inventory_atp_node
)
from src.orchestrator.graph import run_agent_pipeline, build_agent_graph
from src.erp_adapters.opentrans_xml import generate_opentrans_order_xml
from src.erp_adapters.sap_b1_json import generate_sap_b1_order_json
from src.ingestion.schemas import RawExtractedDocument, CustomerReference, ExtractedLineItem, InputChannel


# ------------------------------------------------------------------------------
# 1. Intent Classification Tests
# ------------------------------------------------------------------------------
def test_classify_intent_order():
    state: AgentState = {
        "task_id": "t1",
        "raw_content": "Guten Tag, wir möchten gerne 50 Stück Schrauben M8 bestellen.",
        "execution_trace": []
    }
    res = classify_intent_node(state)
    assert res["intent"] == IntentType.NEW_ORDER
    assert "classify_intent" in res["execution_trace"]


def test_classify_intent_rma():
    state: AgentState = {
        "task_id": "t2",
        "raw_content": "Reklamation: Die gelieferten Dichtungen sind defekt und beschädigt.",
        "execution_trace": []
    }
    res = classify_intent_node(state)
    assert res["intent"] == IntentType.RETURN_RMA


def test_classify_intent_stock():
    state: AgentState = {
        "task_id": "t3",
        "raw_content": "Haben Sie 100 Kugellager 6204-2RS auf Lager verfügbar?",
        "execution_trace": []
    }
    res = classify_intent_node(state)
    assert res["intent"] == IntentType.STOCK_INQUIRY


# ------------------------------------------------------------------------------
# 2. ERP Adapters Tests (OpenTRANS XML & SAP B1 JSON)
# ------------------------------------------------------------------------------
def test_opentrans_xml_generation():
    line_items = [
        {
            "line_number": 1,
            "matched_sku": "ART-DIN-933-M8X30",
            "title_de": "Sechskantschraube DIN 933 M8x30",
            "base_quantity": 1000.0,
            "base_uom": "STK",
            "unit_price_net": 0.18,
            "total_price_net": 180.0,
            "tax_rate": 19.0
        }
    ]

    xml_output = generate_opentrans_order_xml(
        order_id="AUF-2026-901",
        customer_id="DE-10021",
        customer_name="Müller Maschinenbau GmbH & Co. KG",
        order_date="2026-11-07",
        delivery_date="2026-11-14",
        line_items=line_items,
        total_net_amount=180.0
    )

    assert "<?xml version=" in xml_output
    assert "<ORDER" in xml_output
    assert 'version="2.1"' in xml_output
    assert "<ORDER_ID>AUF-2026-901</ORDER_ID>" in xml_output
    assert "<SUPPLIER_AID>ART-DIN-933-M8X30</SUPPLIER_AID>" in xml_output
    assert "<PRICE_LINE_AMOUNT>180.00</PRICE_LINE_AMOUNT>" in xml_output
    assert "<TOTAL_AMOUNT>180.00</TOTAL_AMOUNT>" in xml_output


def test_sap_b1_json_generation():
    line_items = [
        {
            "matched_sku": "ART-DIN-933-M8X30",
            "title_de": "Sechskantschraube DIN 933 M8x30",
            "base_quantity": 500.0,
            "unit_price_net": 0.20,
            "tax_rate": 19.0,
            "base_uom": "STK"
        }
    ]

    json_str = generate_sap_b1_order_json(
        customer_id="DE-10021",
        customer_order_number="PO-7712",
        order_date="2026-11-07",
        delivery_date="2026-11-15",
        line_items=line_items
    )

    assert '"CardCode": "DE-10021"' in json_str
    assert '"NumAtCard": "PO-7712"' in json_str
    assert '"ItemCode": "ART-DIN-933-M8X30"' in json_str
    assert '"Quantity": 500.0' in json_str


# ------------------------------------------------------------------------------
# 3. Confidence Gate Policy Tests
# ------------------------------------------------------------------------------
def test_confidence_gate_auto_approval():
    state: AgentState = {
        "task_id": "cg1",
        "overall_confidence": 0.98,
        "total_net_amount": 450.00,
        "resolved_items": [{"requires_human_review": False}],
        "inventory_checks": [{"sku": "ART-1", "in_stock": True}],
        "execution_trace": []
    }
    res = confidence_gate_node(state)
    assert res["status"] == WorkflowStatus.READY_FOR_EXPORT
    assert res["requires_human_review"] is False
    assert len(res["review_reasons"]) == 0


def test_confidence_gate_low_confidence_flagged():
    state: AgentState = {
        "task_id": "cg2",
        "overall_confidence": 0.88,  # Below 0.95 threshold
        "total_net_amount": 300.00,
        "resolved_items": [{"requires_human_review": False}],
        "inventory_checks": [{"sku": "ART-1", "in_stock": True}],
        "execution_trace": []
    }
    res = confidence_gate_node(state)
    assert res["status"] == WorkflowStatus.NEEDS_HUMAN_REVIEW
    assert res["requires_human_review"] is True
    assert any("Konfidenz" in r for r in res["review_reasons"])


def test_confidence_gate_high_value_flagged():
    state: AgentState = {
        "task_id": "cg3",
        "overall_confidence": 0.99,
        "total_net_amount": 3500.00,  # Exceeds 2,500.00 EUR limit
        "resolved_items": [{"requires_human_review": False}],
        "inventory_checks": [{"sku": "ART-1", "in_stock": True}],
        "execution_trace": []
    }
    res = confidence_gate_node(state)
    assert res["status"] == WorkflowStatus.NEEDS_HUMAN_REVIEW
    assert res["requires_human_review"] is True
    assert any("Auftragswert" in r for r in res["review_reasons"])


def test_confidence_gate_stockout_flagged():
    state: AgentState = {
        "task_id": "cg4",
        "overall_confidence": 0.98,
        "total_net_amount": 200.00,
        "resolved_items": [{"requires_human_review": False}],
        "inventory_checks": [{"sku": "ART-1", "in_stock": False, "atp": 0}],
        "execution_trace": []
    }
    res = confidence_gate_node(state)
    assert res["status"] == WorkflowStatus.NEEDS_HUMAN_REVIEW
    assert res["requires_human_review"] is True
    assert any("nicht ausreichend verfügbar" in r for r in res["review_reasons"])


# ------------------------------------------------------------------------------
# 4. End-to-End Orchestrator Pipeline Execution Test
# ------------------------------------------------------------------------------
@patch("src.orchestrator.nodes.MultiChannelParser")
def test_end_to_end_orchestrator_pipeline(mock_parser_cls):
    """Verifies complete LangGraph state machine execution from input to output."""
    mock_parser_instance = MagicMock()
    mock_parser_instance.parse.return_value = RawExtractedDocument(
        channel=InputChannel.EMAIL,
        customer=CustomerReference(company_name="Müller Maschinenbau GmbH & Co. KG"),
        customer_order_number="PO-2026-TEST",
        order_date="2026-11-07",
        line_items=[
            ExtractedLineItem(
                line_number=1,
                raw_description="O-Ring Dichtungen MM-O-687",
                raw_item_number="MM-O-687",
                quantity=2,
                raw_uom="Dosen"
            )
        ]
    )
    mock_parser_cls.return_value = mock_parser_instance

    raw_order_email = "Bestellung: 2 Dosen MM-O-687 für Werk Stuttgart."

    final_state = run_agent_pipeline(
        raw_content=raw_order_email,
        customer_id="DE-10021",
        channel="email",
        export_format="opentrans_xml"
    )

    assert final_state["task_id"] is not None
    assert final_state["intent"] == IntentType.NEW_ORDER
    assert "classify_intent" in final_state["execution_trace"]
    assert "ingest_and_resolve" in final_state["execution_trace"]
    assert "check_inventory_atp" in final_state["execution_trace"]
    assert "confidence_gate" in final_state["execution_trace"]
    assert len(final_state["resolved_items"]) == 1
    assert final_state["resolved_items"][0]["matched_sku"] == "ART-O-RING-22X3_0-BRAUN-1087"
    assert final_state["status"] in (WorkflowStatus.EXPORTED, WorkflowStatus.NEEDS_HUMAN_REVIEW)
