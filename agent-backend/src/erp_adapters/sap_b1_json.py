"""
BetriebsPilot AI - SAP Business One Service Layer JSON Generator
Generates valid JSON payloads for the SAP B1 Service Layer REST API (POST /b1s/v2/Orders).
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional


def generate_sap_b1_order_json(
    customer_id: str,
    customer_order_number: Optional[str],
    order_date: Optional[str],
    delivery_date: Optional[str],
    line_items: List[Dict[str, Any]],
    comments: Optional[str] = None
) -> str:
    """
    Constructs an SAP Business One Service Layer JSON payload for Document Type 17 (Sales Order).
    """
    doc_date = order_date or datetime.now().strftime("%Y-%m-%d")
    due_date = delivery_date or doc_date

    document_lines = []
    for idx, item in enumerate(line_items):
        document_lines.append({
            "LineNum": idx,
            "ItemCode": item.get("matched_sku"),
            "ItemDescription": item.get("title_de", item.get("raw_description")),
            "Quantity": float(item.get("base_quantity", 1.0)),
            "UnitPrice": float(item.get("unit_price_net", 0.0)),
            "TaxCode": "A1" if float(item.get("tax_rate", 19.0)) == 19.0 else "A2",  # Standard German SAP B1 Tax Codes
            "WarehouseCode": "01",
            "UoMEntry": item.get("base_uom", "STK")
        })

    payload = {
        "CardCode": customer_id,
        "DocDate": doc_date,
        "DocDueDate": due_date,
        "NumAtCard": customer_order_number or "",
        "Comments": comments or "Created automatically by BetriebsPilot AI",
        "DocumentLines": document_lines
    }

    return json.dumps(payload, indent=2, ensure_ascii=False)
