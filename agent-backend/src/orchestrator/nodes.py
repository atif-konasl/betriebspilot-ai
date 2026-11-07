"""
BetriebsPilot AI - LangGraph Orchestrator Nodes
Modular transformer functions operating on AgentState:
  1. classify_intent
  2. ingest_and_resolve
  3. check_inventory_atp
  4. confidence_gate
  5. generate_legacy_file
  6. human_review
"""

import os
import re
import logging
from typing import Dict, Any, List

import psycopg
from psycopg.rows import dict_row

from src.orchestrator.state import AgentState, IntentType, WorkflowStatus
from src.ingestion.parser import MultiChannelParser
from src.ingestion.schemas import InputChannel
from src.rag.hybrid_retriever import ThreeTierCascadeResolver
from src.erp_adapters.opentrans_xml import generate_opentrans_order_xml
from src.erp_adapters.sap_b1_json import generate_sap_b1_order_json

logger = logging.getLogger("betriebspilot.orchestrator.nodes")

# ------------------------------------------------------------------------------
# 1. Intent Classifier Node
# ------------------------------------------------------------------------------
RMA_KEYWORDS = ["reklamation", "beschädigt", "retoure", "gutschrift", "falsch geliefert", "rücksendung", "defekt"]
STOCK_KEYWORDS = ["haben sie", "verfügbar", "lieferzeit", "auf lager", "bestand", "lieferbar"]
INVOICE_KEYWORDS = ["rechnungskopie", "mahnung", "kontoauszug", "zahlungsziel", "rechnung bezahlt"]

def classify_intent_node(state: AgentState) -> Dict[str, Any]:
    """Classifies incoming text into NEW_ORDER, RETURN_RMA, STOCK_INQUIRY, or INVOICE_QUERY."""
    text_lower = state["raw_content"].lower()
    trace = state["execution_trace"] + ["classify_intent"]

    if any(k in text_lower for k in RMA_KEYWORDS):
        intent = IntentType.RETURN_RMA
    elif any(k in text_lower for k in STOCK_KEYWORDS):
        intent = IntentType.STOCK_INQUIRY
    elif any(k in text_lower for k in INVOICE_KEYWORDS):
        intent = IntentType.INVOICE_QUERY
    else:
        intent = IntentType.NEW_ORDER

    logger.info(f"Task '{state['task_id']}': Classified intent -> {intent.value}")
    return {
        "intent": intent,
        "execution_trace": trace
    }


# ------------------------------------------------------------------------------
# 2. Ingest & 3-Tier RAG Resolution Node
# ------------------------------------------------------------------------------
def ingest_and_resolve_node(state: AgentState) -> Dict[str, Any]:
    """Runs MultiChannelParser and ThreeTierCascadeResolver to extract and resolve items."""
    trace = state["execution_trace"] + ["ingest_and_resolve"]
    channel = state.get("channel", "email")
    customer_id = state["customer_id"]

    try:
        # 1. Parse Unstructured Content
        parser = MultiChannelParser()
        raw_doc = parser.parse(content=state["raw_content"], channel=channel)

        # 2. Resolve via 3-Tier Cascade
        resolver = ThreeTierCascadeResolver()
        resolved_items, summary = resolver.resolve_document(customer_id=customer_id, document=raw_doc)

        resolved_dicts = [item.model_dump() for item in resolved_items]
        doc_dict = raw_doc.model_dump()

        logger.info(
            f"Task '{state['task_id']}': Resolved {summary.resolved_items}/{summary.total_items} items "
            f"(Confidence: {summary.overall_confidence:.1%}, Net: {summary.total_net_amount:.2f} EUR)"
        )

        return {
            "status": WorkflowStatus.RESOLVED,
            "extracted_document": doc_dict,
            "resolved_items": resolved_dicts,
            "overall_confidence": summary.overall_confidence,
            "total_net_amount": summary.total_net_amount,
            "total_gross_amount": summary.total_gross_amount,
            "execution_trace": trace
        }

    except Exception as e:
        logger.error(f"Error in ingest_and_resolve_node: {e}")
        return {
            "status": WorkflowStatus.FAILED,
            "error_message": str(e),
            "execution_trace": trace
        }


# ------------------------------------------------------------------------------
# 3. Real-Time Available-To-Promise (ATP) Inventory Check Node
# ------------------------------------------------------------------------------
def check_inventory_atp_node(state: AgentState) -> Dict[str, Any]:
    """
    Checks PostgreSQL erp_inventory for physical, reserved, and incoming stock.
    Formula: ATP = physical_stock - reserved_stock + incoming_stock
    """
    trace = state["execution_trace"] + ["check_inventory_atp"]
    resolved_items = list(state.get("resolved_items", []))
    inventory_checks: List[Dict[str, Any]] = []

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "betriebspilot")
    password = os.getenv("POSTGRES_PASSWORD", "betriebspilot_secret")
    db = os.getenv("POSTGRES_DB", "betriebspilot_erp")
    conn_str = f"postgresql://{user}:{password}@{host}:{port}/{db}"

    with psycopg.connect(conn_str, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for item in resolved_items:
                sku = item.get("matched_sku")
                base_qty = float(item.get("base_quantity", 1.0))

                if not sku or sku == "UNRESOLVED":
                    inventory_checks.append({
                        "sku": "UNRESOLVED",
                        "atp": 0,
                        "in_stock": False,
                        "status": "UNRESOLVED_ITEM"
                    })
                    continue

                cur.execute("""
                    SELECT physical_stock, reserved_stock, incoming_stock
                    FROM erp_inventory WHERE sku = %s;
                """, (sku,))
                inv = cur.fetchone()

                if inv:
                    phys = int(inv["physical_stock"])
                    res = int(inv["reserved_stock"])
                    inc = int(inv["incoming_stock"])
                    atp = phys - res + inc
                    in_stock = atp >= base_qty

                    inv_status = "IN_STOCK" if in_stock else ("PARTIAL_STOCK" if atp > 0 else "OUT_OF_STOCK")
                    
                    if not in_stock:
                        item["requires_human_review"] = True
                        item["review_reason"] = (
                            f"Lieferrückstand: ATP ({atp} {item.get('base_uom')}) < Bestellmenge ({base_qty:.0f} {item.get('base_uom')})."
                        )

                    inventory_checks.append({
                        "sku": sku,
                        "physical_stock": phys,
                        "reserved_stock": res,
                        "incoming_stock": inc,
                        "atp": atp,
                        "required_qty": base_qty,
                        "in_stock": in_stock,
                        "status": inv_status
                    })
                else:
                    inventory_checks.append({
                        "sku": sku,
                        "atp": 0,
                        "in_stock": False,
                        "status": "NOT_IN_WAREHOUSE"
                    })

    logger.info(f"Task '{state['task_id']}': Completed ATP inventory checks for {len(inventory_checks)} items.")
    return {
        "status": WorkflowStatus.ATP_CHECKED,
        "resolved_items": resolved_items,
        "inventory_checks": inventory_checks,
        "execution_trace": trace
    }


# ------------------------------------------------------------------------------
# 4. Confidence & Policy Gate Node
# ------------------------------------------------------------------------------
def confidence_gate_node(state: AgentState) -> Dict[str, Any]:
    """
    Evaluates GoBD compliance rules:
      1. Overall confidence >= 0.95
      2. Order total < MAX_ORDER_AUTO_APPROVE_EUR (2,500 EUR)
      3. All items in stock (ATP >= base_qty)
      4. No items flagged for review
    """
    trace = state["execution_trace"] + ["confidence_gate"]
    reasons: List[str] = []

    conf_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.95"))
    max_auto_eur = float(os.getenv("MAX_ORDER_AUTO_APPROVE_EUR", "2500.00"))

    confidence = state.get("overall_confidence", 0.0)
    total_net = state.get("total_net_amount", 0.0)
    resolved_items = state.get("resolved_items", [])
    inventory_checks = state.get("inventory_checks", [])

    # Check 1: Confidence
    if confidence < conf_threshold:
        reasons.append(f"Gesamt-Konfidenz ({confidence:.1%}) unter Schwellenwert von {conf_threshold:.1%}.")

    # Check 2: High Value Gate
    if total_net >= max_auto_eur:
        reasons.append(f"Auftragswert ({total_net:.2f} EUR) übersteigt Limit von {max_auto_eur:.2f} EUR (4-Augen-Prinzip).")

    # Check 3: Inventory Stockout
    for inv in inventory_checks:
        if not inv.get("in_stock", True):
            reasons.append(f"Artikel '{inv.get('sku')}' nicht ausreichend verfügbar (ATP: {inv.get('atp')}).")

    # Check 4: Item-level review flags
    for item in resolved_items:
        if item.get("requires_human_review") and item.get("review_reason"):
            reasons.append(f"Pos {item.get('line_number')}: {item.get('review_reason')}")

    # Remove duplicates while preserving order
    unique_reasons = list(dict.fromkeys(reasons))

    if unique_reasons:
        logger.info(f"Task '{state['task_id']}': Routed to Human Review ({len(unique_reasons)} reasons).")
        return {
            "status": WorkflowStatus.NEEDS_HUMAN_REVIEW,
            "requires_human_review": True,
            "review_reasons": unique_reasons,
            "execution_trace": trace
        }
    else:
        logger.info(f"Task '{state['task_id']}': Auto-Approved! Ready for ERP export.")
        return {
            "status": WorkflowStatus.READY_FOR_EXPORT,
            "requires_human_review": False,
            "review_reasons": [],
            "execution_trace": trace
        }


# ------------------------------------------------------------------------------
# 5. Legacy ERP Payload Generator Node
# ------------------------------------------------------------------------------
def generate_legacy_file_node(state: AgentState) -> Dict[str, Any]:
    """Generates OpenTRANS 2.1 XML or SAP Business One JSON payload."""
    trace = state["execution_trace"] + ["generate_legacy_file"]
    fmt = state.get("export_format", "opentrans_xml").lower()
    doc = state.get("extracted_document") or {}
    customer = doc.get("customer") or {}
    
    order_id = doc.get("customer_order_number") or f"AUF-{state['task_id'][:8].upper()}"
    cust_id = state["customer_id"]
    cust_name = customer.get("company_name") or f"Kunde {cust_id}"
    order_date = doc.get("order_date")
    delivery_date = doc.get("requested_delivery_date")
    line_items = state.get("resolved_items", [])
    total_net = state.get("total_net_amount", 0.0)

    if fmt == "sap_b1_json":
        payload = generate_sap_b1_order_json(
            customer_id=cust_id,
            customer_order_number=order_id,
            order_date=order_date,
            delivery_date=delivery_date,
            line_items=line_items
        )
    else:
        # Default: OpenTRANS 2.1 XML for Sage 100 / proALPHA
        payload = generate_opentrans_order_xml(
            order_id=order_id,
            customer_id=cust_id,
            customer_name=cust_name,
            order_date=order_date,
            delivery_date=delivery_date,
            line_items=line_items,
            total_net_amount=total_net
        )

    logger.info(f"Task '{state['task_id']}': Generated {fmt} payload ({len(payload)} bytes).")
    return {
        "status": WorkflowStatus.EXPORTED,
        "generated_export_payload": payload,
        "execution_trace": trace
    }


# ------------------------------------------------------------------------------
# 6. Human-in-the-Loop Review Node (Pause / Staging)
# ------------------------------------------------------------------------------
def human_review_node(state: AgentState) -> Dict[str, Any]:
    """Staging node for orders requiring clerk verification in the Split-Screen UI."""
    trace = state["execution_trace"] + ["human_review"]
    logger.info(f"Task '{state['task_id']}': In human review staging queue.")
    return {
        "status": WorkflowStatus.NEEDS_HUMAN_REVIEW,
        "execution_trace": trace
    }
