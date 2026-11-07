"""
BetriebsPilot AI - RAG Resolution Schemas & Data Contracts
Represents the deterministically resolved ERP line items, packaging unit math,
and resolution confidence summaries.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ResolutionTier(str, Enum):
    """The 3-tier cascade tier where the SKU was matched."""
    TIER_1_DIRECT_ALIAS = "TIER_1_DIRECT_ALIAS"    # Customer-specific SKU Map (100% confidence)
    TIER_2_ORDER_HISTORY = "TIER_2_ORDER_HISTORY"  # 24-month order history (95% confidence)
    TIER_3_QDRANT_HYBRID = "TIER_3_QDRANT_HYBRID"  # Semantic vector search (similarity score)
    UNRESOLVED = "UNRESOLVED"                      # No match found in catalog


class ResolvedLineItem(BaseModel):
    """
    Final resolved ERP line item with verified internal SKU, base quantity math,
    catalog pricing, and human-in-the-loop review flags.
    """
    model_config = ConfigDict(populate_by_name=True)

    line_number: int = Field(description="Line number matching original document")
    raw_description: str = Field(description="Verbatim text from customer order")
    raw_item_number: Optional[str] = Field(default=None, description="Customer SKU if provided")
    
    # Resolved ERP Catalog Data
    matched_sku: str = Field(description="Internal ERP SKU code (e.g. ART-DIN-933-M8X30-88-1004)")
    title_de: str = Field(description="Official German catalog product title")
    category: str = Field(description="Product category (e.g. Befestigungstechnik)")
    resolution_tier: ResolutionTier = Field(description="Cascade tier that resolved the SKU")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall item confidence score")
    
    # Deterministic Packaging Math
    ordered_quantity: float = Field(gt=0, description="Quantity written on customer order")
    ordered_uom: str = Field(description="Unit of measure on customer order (e.g. Karton)")
    base_uom: str = Field(default="STK", description="ERP inventory base unit (e.g. STK, MTR)")
    packaging_factor: int = Field(default=1, ge=1, description="Quantity per packaging unit (e.g. 100 STK/Ktn)")
    base_quantity: float = Field(gt=0, description="Calculated base quantity (ordered_qty * packaging_factor)")
    
    # Pricing & Taxes
    unit_price_net: float = Field(ge=0.0, description="Catalog net price per base unit")
    total_price_net: float = Field(ge=0.0, description="base_quantity * unit_price_net")
    tax_rate: float = Field(default=19.0, description="VAT percentage (standard 19% or reduced 7%)")
    
    # HITL Governance
    requires_human_review: bool = Field(default=False, description="True if flagged for clerk verification")
    review_reason: Optional[str] = Field(default=None, description="Reason why human verification is required")


class ResolutionSummary(BaseModel):
    """High-level summary of the resolution process across an entire purchase order."""
    total_items: int = Field(default=0)
    resolved_items: int = Field(default=0)
    tier_1_matches: int = Field(default=0)
    tier_2_matches: int = Field(default=0)
    tier_3_matches: int = Field(default=0)
    items_needing_review: int = Field(default=0)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    total_net_amount: float = Field(default=0.0)
    total_gross_amount: float = Field(default=0.0)
