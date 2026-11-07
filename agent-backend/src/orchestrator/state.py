"""
BetriebsPilot AI - LangGraph Agent State Definition
Strict TypedDict representing the centralized state machine blackboard across all nodes.
"""

from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any


class IntentType(str, Enum):
    """Classified business intent of the incoming communication."""
    NEW_ORDER = "NEW_ORDER"           # Commercial sales order
    RETURN_RMA = "RETURN_RMA"         # Damaged goods / return claim
    STOCK_INQUIRY = "STOCK_INQUIRY"   # Inventory availability request
    INVOICE_QUERY = "INVOICE_QUERY"   # Billing question / invoice copy request


class WorkflowStatus(str, Enum):
    """Lifecycle status of the agent execution graph."""
    INITIALIZED = "INITIALIZED"
    PARSED = "PARSED"
    RESOLVED = "RESOLVED"
    ATP_CHECKED = "ATP_CHECKED"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"       # Auto-approved (Confidence >= 0.95 & in stock)
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"   # Paused for Split-Screen clerk verification
    EXPORTED = "EXPORTED"                       # Written to ERP hotfolder
    FAILED = "FAILED"


class AgentState(TypedDict):
    """
    The shared state dictionary passed across all LangGraph nodes.
    Maintains 100% GoBD auditability from raw input to generated ERP file.
    """
    task_id: str
    raw_content: str
    channel: str                          # 'pdf', 'email', 'whatsapp', 'sms'
    customer_id: str                      # Verified ERP Customer ID (e.g. 'DE-10021')
    
    # Classification & Lifecycle
    intent: Optional[IntentType]
    status: WorkflowStatus
    
    # Ingestion & RAG Results
    extracted_document: Optional[Dict[str, Any]]
    resolved_items: List[Dict[str, Any]]
    inventory_checks: List[Dict[str, Any]]
    
    # Governance & Autonomy Guardrails
    overall_confidence: float
    total_net_amount: float
    total_gross_amount: float
    requires_human_review: bool
    review_reasons: List[str]
    
    # Output Generation
    export_format: str                    # 'opentrans_xml' (Sage/proALPHA) or 'sap_b1_json' (SAP)
    generated_export_payload: Optional[str]
    
    # Observability & Trace
    execution_trace: List[str]
    error_message: Optional[str]
