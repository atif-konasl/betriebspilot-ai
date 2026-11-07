"""
Unit tests for BetriebsPilot AI multi-channel ingestion parser and preprocessors.
"""

import io
from unittest.mock import MagicMock
import pytest
import pypdf

from src.ingestion.schemas import (
    InputChannel,
    ExtractedLineItem,
    CustomerReference,
    RawExtractedDocument
)
from src.ingestion.preprocessors import (
    extract_text_from_pdf,
    clean_email_text,
    clean_chat_text
)
from src.ingestion.parser import MultiChannelParser
from src.llm.client import LLMClient


# ------------------------------------------------------------------------------
# 1. Schema & Validation Tests
# ------------------------------------------------------------------------------
def test_extracted_line_item_german_number_parsing():
    """Verify German comma decimals and currency strings are coerced accurately."""
    item = ExtractedLineItem(
        line_number=1,
        raw_description="Sechskantschrauben M8x30",
        quantity="12,5",  # German comma format
        raw_uom="Karton",
        unit_price_quoted="14,80 €"
    )
    assert item.quantity == 12.5
    assert item.unit_price_quoted == 14.80

    # Test thousands separator with comma
    item2 = ExtractedLineItem(
        line_number=2,
        raw_description="Unterlegscheiben",
        quantity="1.500",
        raw_uom="STK",
        unit_price_quoted="1.250,50 EUR"
    )
    assert item2.quantity == 1500.0
    assert item2.unit_price_quoted == 1250.50


# ------------------------------------------------------------------------------
# 2. Preprocessor Tests
# ------------------------------------------------------------------------------
def test_clean_email_text():
    """Verify German legal boilerplate and reply headers are stripped."""
    raw_email = """Guten Tag Herr Bauer,

bitte senden Sie uns dringend folgende Artikel:
- 10 Kartons Sechskantschrauben M8x30 verzinkt
- 5 Pakete O-Ringe 22x3mm

Bestellnummer: PO-2026-9912

Mit freundlichen Grüßen,
Markus Schmidt
Schmidt & Söhne GmbH

Diese E-Mail enthält vertrauliche und/oder rechtlich geschützte Informationen.
Amtsgericht Dortmund HRB 12345, Sitz der Gesellschaft: Dortmund.
"""
    cleaned = clean_email_text(raw_email)
    assert "PO-2026-9912" in cleaned
    assert "10 Kartons Sechskantschrauben" in cleaned
    assert "Diese E-Mail enthält vertrauliche" not in cleaned
    assert "Amtsgericht Dortmund" not in cleaned


def test_clean_chat_text():
    """Verify WhatsApp timestamps and contact prefixes are removed."""
    raw_chat = """[14:20, 07.11.2026] Markus Baustelle: Servus! Brauchen auf der Baustelle dringend 20 Dosen O-Ringe 22mm.
[14:21, 07.11.2026] Markus Baustelle: Und noch 50 Stück M8 Bolzen. Bestell-Nr 88120."""

    cleaned = clean_chat_text(raw_chat)
    assert "[14:20" not in cleaned
    assert "Servus! Brauchen auf der Baustelle" in cleaned
    assert "Bestell-Nr 88120" in cleaned


def test_pdf_extraction_in_memory():
    """Create a synthetic PDF in memory and verify text extraction."""
    writer = pypdf.PdfWriter()
    # Add a blank page with some text using annotation / standard page
    page = writer.add_blank_page(width=300, height=300)
    
    # Write to memory buffer
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_buffer.seek(0)

    # Empty page should not crash
    extracted = extract_text_from_pdf(pdf_buffer)
    assert isinstance(extracted, str)


# ------------------------------------------------------------------------------
# 3. MultiChannelParser Tests (Mocked LLM)
# ------------------------------------------------------------------------------
def test_parser_email_end_to_end_mocked():
    """Verify MultiChannelParser pipeline with mocked LLMClient."""
    mock_llm = MagicMock(spec=LLMClient)
    
    expected_doc = RawExtractedDocument(
        channel=InputChannel.EMAIL,
        customer=CustomerReference(
            company_name="Schmidt & Söhne GmbH",
            contact_name="Markus Schmidt",
            email="m.schmidt@schmidt-soehne.de"
        ),
        customer_order_number="PO-2026-9912",
        order_date="2026-11-07",
        line_items=[
            ExtractedLineItem(
                line_number=1,
                raw_description="Sechskantschrauben M8x30 verzinkt",
                quantity=10,
                raw_uom="Karton"
            ),
            ExtractedLineItem(
                line_number=2,
                raw_description="O-Ringe 22x3mm FKM",
                quantity=5,
                raw_uom="Paket"
            )
        ]
    )
    mock_llm.extract_structured.return_value = expected_doc

    parser = MultiChannelParser(llm_client=mock_llm)
    raw_email = "Bestellung PO-2026-9912: 10 Kartons Schrauben, 5 Pakete O-Ringe"

    result = parser.parse(
        content=raw_email,
        channel=InputChannel.EMAIL,
        metadata={"sender_email": "m.schmidt@schmidt-soehne.de"}
    )

    assert result.channel == InputChannel.EMAIL
    assert result.customer_order_number == "PO-2026-9912"
    assert len(result.line_items) == 2
    assert result.line_items[0].line_number == 1
    assert result.line_items[0].raw_uom == "Karton"
    assert result.line_items[1].line_number == 2
    assert result.customer.email == "m.schmidt@schmidt-soehne.de"
    assert result.raw_text_preview is not None


def test_parser_empty_content_raises():
    """Verify parser rejects whitespace or empty input."""
    parser = MultiChannelParser(llm_client=MagicMock())
    with pytest.raises(ValueError) as exc:
        parser.parse(content="   ", channel=InputChannel.EMAIL)
    assert "empty" in str(exc.value).lower()
