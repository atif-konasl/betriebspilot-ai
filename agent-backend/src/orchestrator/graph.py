"""
BetriebsPilot AI - Compiled LangGraph Multi-Agent Orchestrator
Assembles the stateful cyclic state machine connecting Intent Classification,
Multi-Channel Ingestion, 3-Tier Cascade RAG, Inventory ATP Checks, and Legacy ERP File Generation.
"""

import uuid
import logging
from typing import Optional, Dict, Any

from langgraph.graph import StateGraph, START, END

from src.orchestrator.state import AgentState, IntentType, WorkflowStatus
from src.orchestrator.nodes import (
    classify_intent_node,
    ingest_and_resolve_node,
    check_inventory_atp_node,
    confidence_gate_node,
    generate_legacy_file_node,
    human_review_node
)

logger = logging.getLogger("betriebspilot.orchestrator.graph")

# ------------------------------------------------------------------------------
# Conditional Edge Functions
# ------------------------------------------------------------------------------
def route_after_intent(state: AgentState) -> str:
    """Routes based on classified business intent."""
    intent = state.get("intent")
    if intent == IntentType.NEW_ORDER:
        return "ingest_and_resolve"
    # Future expansions for RMA and Stock Inquiry can branch here
    return "ingest_and_resolve"

def route_after_confidence_gate(state: AgentState) -> str:
    """
    Decides whether to auto-export or route to Split-Screen Human Review.
    """
    if state.get("requires_human_review", False):
        return "human_review"
    return "generate_legacy_file"


# ------------------------------------------------------------------------------
# Graph Construction & Compilation
# ------------------------------------------------------------------------------
def build_agent_graph() -> StateGraph:
    """Builds and wires the BetriebsPilot AI LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # 1. Register Nodes
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("ingest_and_resolve", ingest_and_resolve_node)
    workflow.add_node("check_inventory_atp", check_inventory_atp_node)
    workflow.add_node("confidence_gate", confidence_gate_node)
    workflow.add_node("generate_legacy_file", generate_legacy_file_node)
    workflow.add_node("human_review", human_review_node)

    # 2. Wire Edges
    workflow.add_edge(START, "classify_intent")
    workflow.add_conditional_edges(
        "classify_intent",
        route_after_intent,
        {
            "ingest_and_resolve": "ingest_and_resolve"
        }
    )
    workflow.add_edge("ingest_and_resolve", "check_inventory_atp")
    workflow.add_edge("check_inventory_atp", "confidence_gate")
    workflow.add_conditional_edges(
        "confidence_gate",
        route_after_confidence_gate,
        {
            "generate_legacy_file": "generate_legacy_file",
            "human_review": "human_review"
        }
    )
    workflow.add_edge("generate_legacy_file", END)
    workflow.add_edge("human_review", END)

    return workflow


# Compile the singleton runnable graph
orchestrator_app = build_agent_graph().compile()


# ------------------------------------------------------------------------------
# High-Level Execution Helper
# ------------------------------------------------------------------------------
def run_agent_pipeline(
    raw_content: str,
    customer_id: str,
    channel: str = "email",
    export_format: str = "opentrans_xml",
    task_id: Optional[str] = None
) -> AgentState:
    """
    Executes the full LangGraph state machine from incoming raw content to final state.
    """
    tid = task_id or str(uuid.uuid4())
    logger.info(f"Initiating agent pipeline execution for Task '{tid}' (Customer: '{customer_id}')")

    initial_state: AgentState = {
        "task_id": tid,
        "raw_content": raw_content,
        "channel": channel,
        "customer_id": customer_id,
        "intent": None,
        "status": WorkflowStatus.INITIALIZED,
        "extracted_document": None,
        "resolved_items": [],
        "inventory_checks": [],
        "overall_confidence": 0.0,
        "total_net_amount": 0.0,
        "total_gross_amount": 0.0,
        "requires_human_review": False,
        "review_reasons": [],
        "export_format": export_format,
        "generated_export_payload": None,
        "execution_trace": [],
        "error_message": None
    }

    final_state = orchestrator_app.invoke(initial_state)
    logger.info(
        f"Pipeline completed for Task '{tid}': Status -> {final_state['status'].value} "
        f"(Trace: {' -> '.join(final_state['execution_trace'])})"
    )
    return final_state
