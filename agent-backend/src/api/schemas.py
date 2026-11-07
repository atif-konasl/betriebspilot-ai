"""
BetriebsPilot AI - API Schemas & Data Contracts
Pydantic v2 schemas for REST requests, responses, Swagger documentation, and SSE streaming.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Health & Diagnostic Schemas
# ------------------------------------------------------------------------------
class HealthStatus(BaseModel):
    """Health check response schema."""
    status: str = Field("healthy", description="Overall system health status")
    environment: str = Field("development", description="Runtime environment")
    version: str = Field("1.0.0", description="API version")
    database: Dict[str, Any] = Field(..., description="PostgreSQL connectivity info")
    qdrant: Dict[str, Any] = Field(..., description="Qdrant vector store connectivity info")
    llm: Dict[str, Any] = Field(..., description="Active LLM provider status")


# ------------------------------------------------------------------------------
# Customer Directory
# ------------------------------------------------------------------------------
class CustomerSummary(BaseModel):
    """Customer summary for desktop UI dropdowns and customer identification."""
    customer_id: str = Field(..., json_schema_extra={"example": "DE-10021"}, description="Unique ERP customer identifier")
    company_name: str = Field(..., json_schema_extra={"example": "Müller Maschinenbau GmbH & Co. KG"}, description="Company trade name")
    city: str = Field(..., json_schema_extra={"example": "Stuttgart"}, description="City / Location")
    vat_id: str = Field(..., json_schema_extra={"example": "DE143589211"}, description="German VAT ID (USt-IdNr.)")
    billing_email: str = Field(..., json_schema_extra={"example": "rechnung@mueller-maschinenbau.de"}, description="Billing email")


# ------------------------------------------------------------------------------
# Processing Response Schemas
# ------------------------------------------------------------------------------
class ProcessInputResponse(BaseModel):
    """Standardized result returned after executing the LangGraph orchestrator."""
    task_id: str = Field(..., description="Unique UUID for this processing job")
    status: str = Field(..., json_schema_extra={"example": "READY_FOR_EXPORT"}, description="Workflow lifecycle status")
    intent: Optional[str] = Field(None, json_schema_extra={"example": "NEW_ORDER"}, description="Classified intent")
    customer_id: str = Field(..., json_schema_extra={"example": "DE-10021"}, description="Identified customer code")
    channel: str = Field(..., json_schema_extra={"example": "email"}, description="Input channel (pdf, email, whatsapp, sms)")
    
    extracted_document: Optional[Dict[str, Any]] = Field(None, description="Raw extracted document prior to resolution")
    resolved_items: List[Dict[str, Any]] = Field(default_factory=list, description="Resolved catalog items with pricing")
    inventory_checks: List[Dict[str, Any]] = Field(default_factory=list, description="Real-time ATP inventory check results")
    
    overall_confidence: float = Field(..., json_schema_extra={"example": 0.965}, description="Average confidence score across all items")
    total_net_amount: float = Field(..., json_schema_extra={"example": 345.50}, description="Total order net amount in EUR")
    total_gross_amount: float = Field(..., json_schema_extra={"example": 411.15}, description="Total order gross amount including 19% VAT")
    
    requires_human_review: bool = Field(..., json_schema_extra={"example": False}, description="True if flagged for clerk review")
    review_reasons: List[str] = Field(default_factory=list, description="Reasons triggering manual review if applicable")
    
    export_format: str = Field("opentrans_xml", json_schema_extra={"example": "opentrans_xml"}, description="Target legacy ERP format")
    generated_export_payload: Optional[str] = Field(None, description="Generated XML/JSON payload if auto-approved")
    execution_trace: List[str] = Field(default_factory=list, description="List of LangGraph nodes executed")


# ------------------------------------------------------------------------------
# Approval & Export Schemas
# ------------------------------------------------------------------------------
class ApprovedLineItem(BaseModel):
    """Individual line item approved or edited by the human clerk in Split-Screen UI."""
    line_number: int = Field(default=1, description="Line number")
    raw_item_number: Optional[str] = Field(None, description="Customer-provided part number to learn")
    matched_sku: str = Field(..., json_schema_extra={"example": "ART-DIN-M8X30-88-1010"}, description="Target internal ERP SKU")
    title_de: str = Field(..., description="Product title")
    base_quantity: float = Field(gt=0, description="Total base quantity to book")
    base_uom: str = Field(default="STK", description="Base unit of measure")
    unit_price_net: float = Field(ge=0.0, description="Unit price net")
    total_price_net: float = Field(ge=0.0, description="Total line net price")
    tax_rate: float = Field(default=19.0, description="Tax rate percentage")


class ApproveAndExportRequest(BaseModel):
    """Payload sent by Desktop App when clerk approves or overrides an order."""
    task_id: str = Field(..., description="Task identifier from processing stage")
    customer_id: str = Field(..., json_schema_extra={"example": "DE-10021"}, description="ERP customer code")
    customer_order_number: Optional[str] = Field(None, json_schema_extra={"example": "PO-2026-9912"}, description="Purchase order number")
    order_date: Optional[str] = Field(None, json_schema_extra={"example": "2026-11-07"}, description="Document date YYYY-MM-DD")
    delivery_date: Optional[str] = Field(None, json_schema_extra={"example": "2026-11-14"}, description="Requested delivery date")
    export_format: str = Field("opentrans_xml", json_schema_extra={"example": "opentrans_xml"}, description="'opentrans_xml' or 'sap_b1_json'")
    approved_line_items: List[ApprovedLineItem] = Field(..., description="List of verified line items")
    learn_aliases: bool = Field(default=True, description="Whether to update erp_customer_sku_map for Tier 1 learning")


class ApproveAndExportResponse(BaseModel):
    """Result returned with final generated ERP file payload ready for hotfolder writing."""
    task_id: str = Field(..., description="Task identifier")
    customer_id: str = Field(..., description="ERP customer code")
    export_format: str = Field(..., description="Export format used")
    learned_alias_count: int = Field(default=0, description="Number of customer part aliases learned/updated")
    file_name: str = Field(..., json_schema_extra={"example": "ORDER_DE-10021_PO-9912.xml"}, description="Target filename for ERP hotfolder")
    payload_content: str = Field(..., description="Raw file contents (OpenTRANS 2.1 XML or SAP B1 JSON)")


# ------------------------------------------------------------------------------
# Catalog Search Schemas
# ------------------------------------------------------------------------------
class CatalogSearchResult(BaseModel):
    """Result item returned by semantic catalog vector search in Qdrant."""
    sku: str = Field(..., json_schema_extra={"example": "ART-DIN-M8X30-88-1010"}, description="Internal ERP SKU")
    title_de: str = Field(..., description="German product title")
    category: str = Field(..., description="Product category")
    base_uom: str = Field(..., description="Base unit of measure")
    packaging_unit: str = Field(..., description="Packaging unit")
    packaging_qty: int = Field(..., description="Quantity per packaging unit")
    unit_price_net: float = Field(..., description="Catalog net price")
    tax_rate: float = Field(..., description="Tax rate")
    score: float = Field(..., description="Vector similarity search score (0.0 - 1.0)")
