"""
BetriebsPilot AI - Ingestion Schemas & Data Contracts
Strict Pydantic v2 schemas representing raw extracted documents across all channels
(PDF, Email, WhatsApp, SMS) prior to ERP catalog resolution.
"""

from enum import Enum
from typing import Optional, List, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict


class InputChannel(str, Enum):
    """Supported multi-channel ingestion sources."""
    PDF = "pdf"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"


class ExtractedLineItem(BaseModel):
    """
    Individual raw line item extracted verbatim from the customer's input.
    Does NOT contain internal ERP catalog SKUs or resolved pricing (GoBD compliance).
    """
    model_config = ConfigDict(populate_by_name=True)

    line_number: int = Field(
        default=1,
        ge=1,
        description="Sequential item number in the order (1-indexed)"
    )
    raw_description: str = Field(
        ...,
        min_length=1,
        description="Verbatim product description or trade name as written by customer"
    )
    raw_item_number: Optional[str] = Field(
        default=None,
        description="Customer's own internal SKU, part number, or catalog reference if provided"
    )
    quantity: float = Field(
        ...,
        gt=0,
        description="Numerical quantity requested (must be positive)"
    )
    raw_uom: str = Field(
        default="STK",
        description="Unit of measure verbatim (e.g. STK, Karton, Paket, Dosen, Rolle, Meter)"
    )
    unit_price_quoted: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Net unit price mentioned or agreed in customer's quote/order if present"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this specific line item extraction"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Line-specific comments (e.g. 'wie im März besprochen', 'dringend')"
    )

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_german_quantity(cls, value: Union[str, float, int]) -> float:
        """Converts German comma decimals (e.g. '12,5') to standard float (12.5)."""
        if isinstance(value, str):
            cleaned = value.strip().replace(".", "").replace(",", ".")
            return float(cleaned)
        return float(value)

    @field_validator("unit_price_quoted", mode="before")
    @classmethod
    def parse_german_price(cls, value: Optional[Union[str, float, int]]) -> Optional[float]:
        """Converts German price strings (e.g. '1.450,50' or '12,90') to float."""
        if value is None or value == "":
            return None
        if isinstance(value, str):
            cleaned = value.strip().replace("€", "").replace("EUR", "").strip()
            # If formatted like 1.250,50 -> strip dot, replace comma with dot
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "," in cleaned:
                cleaned = cleaned.replace(",", ".")
            return float(cleaned)
        return float(value)


class CustomerReference(BaseModel):
    """Customer identity clues extracted from headers, signatures, or metadata."""
    company_name: Optional[str] = Field(
        default=None,
        description="Customer company name extracted from letterhead, signature, or domain"
    )
    contact_name: Optional[str] = Field(
        default=None,
        description="Contact person / ordering agent name"
    )
    email: Optional[str] = Field(
        default=None,
        description="Sender email address"
    )
    vat_id: Optional[str] = Field(
        default=None,
        description="German or EU VAT ID (e.g. DE123456789) if provided"
    )
    customer_number_hint: Optional[str] = Field(
        default=None,
        description="Customer account number at the supplier if referenced"
    )


class RawExtractedDocument(BaseModel):
    """
    Standardized data contract produced by the multi-channel parser.
    Acts as the single unified input for the downstream LangGraph orchestrator.
    """
    channel: InputChannel = Field(
        ...,
        description="Origin channel: pdf, email, whatsapp, or sms"
    )
    customer: CustomerReference = Field(
        default_factory=CustomerReference,
        description="Extracted customer identity clues"
    )
    customer_order_number: Optional[str] = Field(
        default=None,
        description="Customer's purchase order number (Bestell-Nr. / Auftrags-Nr. / PO)"
    )
    order_date: Optional[str] = Field(
        default=None,
        description="Order document date in ISO format YYYY-MM-DD"
    )
    requested_delivery_date: Optional[str] = Field(
        default=None,
        description="Requested delivery date (Liefertermin) in ISO format YYYY-MM-DD if requested"
    )
    currency: str = Field(
        default="EUR",
        description="Currency code (defaults to EUR)"
    )
    special_instructions: Optional[str] = Field(
        default=None,
        description="General instructions (e.g. delivery address notes, packaging requirements)"
    )
    line_items: List[ExtractedLineItem] = Field(
        default_factory=list,
        description="List of extracted order line items"
    )
    raw_text_preview: Optional[str] = Field(
        default=None,
        description="First 500 characters of the raw input text for auditability"
    )
