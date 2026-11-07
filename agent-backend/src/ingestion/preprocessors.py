"""
BetriebsPilot AI - Channel-Specific Preprocessors
Sanitizes raw multi-channel inputs (PDF, Email, WhatsApp, SMS) before structured LLM extraction.
"""

import io
import re
import logging
from pathlib import Path
from typing import Union

import pypdf

logger = logging.getLogger("betriebspilot.ingestion.preprocessors")

# ------------------------------------------------------------------------------
# PDF Text Extraction
# ------------------------------------------------------------------------------
def extract_text_from_pdf(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    """
    Extracts text from a digital PDF file or bytes stream using pypdf.
    Preserves page breaks and tabular layout whitespace.
    """
    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"PDF file does not exist: {path}")
            reader = pypdf.PdfReader(str(path))
        elif isinstance(source, bytes):
            if len(source) == 0:
                raise ValueError("PDF byte content is empty.")
            stream = io.BytesIO(source)
            reader = pypdf.PdfReader(stream)
        elif isinstance(source, io.BytesIO):
            reader = pypdf.PdfReader(source)
        else:
            raise TypeError(f"Unsupported PDF source type: {type(source)}")

        extracted_pages = []
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
            if page_text.strip():
                extracted_pages.append(f"--- [SEITE {idx + 1}] ---\n{page_text.strip()}")

        full_text = "\n\n".join(extracted_pages).strip()
        if not full_text:
            logger.warning("PDF extraction returned empty text (may be a scanned image requiring OCR).")
        return full_text

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise ValueError(f"Failed to extract text from PDF: {str(e)}") from e


# ------------------------------------------------------------------------------
# Email Preprocessing & Sanitization
# ------------------------------------------------------------------------------
DISCLAIMER_PATTERNS = [
    r"(?i)Diese E-Mail enthält vertrauliche.*",
    r"(?i)This email and any attachments are confidential.*",
    r"(?i)Hinweis zum Datenschutz:?.*",
    r"(?i)Rechtlicher Hinweis:?.*",
    r"(?i)Pflichtangaben nach § 35a GmbHG:?.*",
    r"(?i)Amtsgericht.*HRB\s*\d+.*",
    r"(?i)Sitz der Gesellschaft:?.*",
]

REPLY_HEADER_PATTERNS = [
    r"(?m)^-----\s*Ursprüngliche Nachricht\s*-----.*",
    r"(?m)^Von:\s+.*?\nGesendet:\s+.*?\nAn:\s+.*?\nBetreff:\s+.*",
    r"(?m)^From:\s+.*?\nSent:\s+.*?\nTo:\s+.*?\nSubject:\s+.*",
    r"(?m)^Am\s+\d{1,2}\.\d{1,2}\.\d{2,4}.*?schrieb.*?:",
]

def clean_email_text(raw_text: str) -> str:
    """
    Sanitizes raw email bodies by removing legal disclaimers, German company registration
    boilerplate (HRB/GmbHG), and quoted reply threads to reduce LLM token overhead.
    """
    cleaned = raw_text

    # 1. Strip forwarded / reply quote headers
    for pattern in REPLY_HEADER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)

    # 2. Strip legal disclaimers
    for pattern in DISCLAIMER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)

    # 3. Collapse multiple whitespace and newlines
    cleaned = re.sub(r"\r\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    return cleaned.strip()


# ------------------------------------------------------------------------------
# Chat / SMS Preprocessing
# ------------------------------------------------------------------------------
WHATSAPP_TIMESTAMP_PATTERNS = [
    # [14:20, 07.11.2026] Markus: or [07.11.2026, 14:20:15] Markus:
    r"(?m)^\[\d{1,2}:\d{2}(?::\d{2})?,\s+\d{1,2}\.\d{1,2}\.\d{2,4}\]\s+[^:]+:\s*",
    r"(?m)^\[\d{1,2}\.\d{1,2}\.\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\]\s+[^:]+:\s*",
    # 07.11.26, 14:20 - Markus:
    r"(?m)^\d{1,2}\.\d{1,2}\.\d{2,4},?\s+\d{1,2}:\d{2}\s+-\s+[^:]+:\s*",
]

def clean_chat_text(raw_text: str) -> str:
    """
    Sanitizes WhatsApp and SMS transcripts by stripping mobile timestamps and sender prefixes.
    """
    cleaned = raw_text

    # Strip timestamps like "[14:20, 12.03.2024] Markus:"
    for pattern in WHATSAPP_TIMESTAMP_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)

    # Collapse excessive spaces
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()
