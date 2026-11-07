"""
BetriebsPilot AI - Multi-Channel Ingestion Parser
Extracts structured purchase orders, return requests, and inquiries from German PDFs,
emails, WhatsApp, and SMS messages into strict Pydantic schemas using Instructor.
"""

import io
import logging
from pathlib import Path
from typing import Union, Optional, Dict, Any

from src.ingestion.schemas import (
    InputChannel,
    RawExtractedDocument,
    CustomerReference,
    ExtractedLineItem
)
from src.ingestion.preprocessors import (
    extract_text_from_pdf,
    clean_email_text,
    clean_chat_text
)
from src.llm.client import LLMClient, get_llm_client

logger = logging.getLogger("betriebspilot.ingestion.parser")

GERMAN_EXTRACTION_SYSTEM_PROMPT = """Du bist ein präziser digitaler Sachbearbeiter für deutsche Industrie-Großhändler und Zulieferer (Mittelstand Großhandel).
Deine Aufgabe ist die deterministische Extraktion von Bestellungen, Lieferterminen, Kundendaten und Artikellisten aus unstrukturierten Dokumenten (PDFs, E-Mails, WhatsApp/SMS).

STRIKTE REGELN FÜR DIE EXTRAKTION (GoBD-KONFORMITÄT):
1. EXTRAHIERE NUR WAS TATSÄCHLICH VORHANDEN IST: Erfinde NIEMALS Artikelnummern, Mengen oder Sonderkonditionen.
2. ARTIKELBESCHREIBUNG (raw_description): Kopiere die Bezeichnung des Kunden wortwörtlich (inkl. DIN-Normen, Abmessungen, Werkstoffen).
3. MENGE & VERPACKUNGSEINHEIT (quantity & raw_uom):
   - Wenn der Kunde "10 Kartons" schreibt: Menge = 10, Einheit = "Karton". Wandle Einheiten NICHT um!
   - Erhalte Einheiten wie: STK, Karton, Paket, Dose, Rolle, Meter, Set.
4. KUNDENDATEN: Suche im Briefkopf, in der Signatur oder im E-Mail-Absender nach Firmenname, Ansprechpartner, E-Mail und USt-IdNr (z.B. DE123456789).
5. BESTELLNUMMER & TERMINE:
   - Suche nach Kunden-Bestellnummern (PO-Nummer / Bestell-Nr. / Auftrags-Nr.).
   - Wenn ein Liefertermin gewünscht ist (z.B. "bis 15.11.2026", "KW 46"), wandle ihn möglichst in das Format YYYY-MM-DD um.
6. NOTIZEN & SONDERHINWEISE: Notiere Hinweise wie "dringend", "Lieferung an Tor 3", "wie im Angebot vom März".
"""

class MultiChannelParser:
    """
    Unified Ingestion Parser transforming PDFs, Emails, WhatsApp, and SMS into
    strictly validated RawExtractedDocument instances.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or get_llm_client()

    def parse(
        self,
        content: Union[str, bytes, Path, io.BytesIO],
        channel: Union[InputChannel, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> RawExtractedDocument:
        """
        Parses raw unstructured content from any channel into a RawExtractedDocument.

        Args:
            content: Raw text string, PDF file path, or raw PDF bytes/stream.
            channel: Origin channel ('pdf', 'email', 'whatsapp', 'sms').
            metadata: Optional dictionary with channel metadata (e.g. sender email, phone number).

        Returns:
            RawExtractedDocument: Fully populated, strongly validated Pydantic model.
        """
        if isinstance(channel, InputChannel):
            channel_enum = channel
        elif isinstance(channel, str):
            # Handles "email", "EMAIL", "InputChannel.EMAIL", etc.
            val = channel.split(".")[-1].lower()
            channel_enum = InputChannel(val)
        else:
            raise TypeError(f"Expected InputChannel or str, got {type(channel)}")
        logger.info(f"Starting ingestion parsing for channel: {channel_enum.value}")

        # 1. Channel-Specific Preprocessing & Text Extraction
        cleaned_text = self._preprocess_content(content, channel_enum)

        if not cleaned_text.strip():
            raise ValueError(f"Extracted content is empty for channel '{channel_enum.value}'.")

        logger.info(f"Preprocessed text ({len(cleaned_text)} characters). Invoking Instructor LLM extraction...")

        # 2. Build Multi-Modal Prompt with Domain Guardrails
        meta_context = ""
        if metadata:
            meta_context = f"\nZUSÄTZLICHE METADATEN DES KANALS:\n{metadata}\n"

        user_prompt = f"""Kanal: {channel_enum.value.upper()}
{meta_context}
DOKUMENTENTEXT:
\"\"\"
{cleaned_text}
\"\"\"

Bitte extrahiere die Bestellung vollständig in das vorgegebene Schema.
"""

        messages = [
            {"role": "system", "content": GERMAN_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # 3. Instructor Structured Extraction
        extracted_doc = self.llm_client.extract_structured(
            response_model=RawExtractedDocument,
            messages=messages
        )

        # 4. Enrich & Post-Process
        extracted_doc.channel = channel_enum
        extracted_doc.raw_text_preview = cleaned_text[:500]

        # Merge metadata sender info if missing from text
        if metadata:
            if not extracted_doc.customer.email and "sender_email" in metadata:
                extracted_doc.customer.email = metadata["sender_email"]
            if not extracted_doc.customer.company_name and "company_name" in metadata:
                extracted_doc.customer.company_name = metadata["company_name"]

        # Ensure sequential line numbers
        for idx, item in enumerate(extracted_doc.line_items, start=1):
            item.line_number = idx

        logger.info(
            f"Successfully extracted {len(extracted_doc.line_items)} line items "
            f"(Customer: '{extracted_doc.customer.company_name or 'Unknown'}', PO: '{extracted_doc.customer_order_number or 'N/A'}')"
        )
        return extracted_doc

    def _preprocess_content(
        self,
        content: Union[str, bytes, Path, io.BytesIO],
        channel: InputChannel
    ) -> str:
        """Dispatches content to the appropriate cleaner based on input channel."""
        if channel == InputChannel.PDF:
            return extract_text_from_pdf(content)

        elif channel == InputChannel.EMAIL:
            raw_str = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            return clean_email_text(raw_str)

        elif channel in (InputChannel.WHATSAPP, InputChannel.SMS):
            raw_str = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            return clean_chat_text(raw_str)

        else:
            raise ValueError(f"Unsupported channel: {channel}")
