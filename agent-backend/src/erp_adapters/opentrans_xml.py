"""
BetriebsPilot AI - OpenTRANS 2.1 XML Generator
Generates valid OpenTRANS 2.1 XML purchase orders for Sage 100, proALPHA, and abas ERP
hotfolder ingestion (C:\\ERP_Import\\Incoming_Orders\\ or /tmp/erp_import/).
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET
from xml.dom import minidom


def generate_opentrans_order_xml(
    order_id: str,
    customer_id: str,
    customer_name: str,
    order_date: Optional[str],
    delivery_date: Optional[str],
    line_items: List[Dict[str, Any]],
    total_net_amount: float,
    currency: str = "EUR"
) -> str:
    """
    Constructs a fully compliant OpenTRANS 2.1 XML document.
    """
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    doc_date = order_date or datetime.now().strftime("%Y-%m-%d")

    root = ET.Element("ORDER", {
        "version": "2.1",
        "type": "standard",
        "xmlns": "http://www.opentrans.org/XMLSchema/2.1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"
    })

    # 1. ORDER_HEADER
    header = ET.SubElement(root, "ORDER_HEADER")
    
    control_info = ET.SubElement(header, "CONTROL_INFO")
    ET.SubElement(control_info, "GENERATION_DATE").text = now_iso

    order_info = ET.SubElement(header, "ORDER_INFO")
    ET.SubElement(order_info, "ORDER_ID").text = order_id
    ET.SubElement(order_info, "ORDER_DATE").text = doc_date
    if delivery_date:
        delivery_elem = ET.SubElement(order_info, "DELIVERY_DATE")
        ET.SubElement(delivery_elem, "DELIVERY_START_DATE").text = delivery_date

    parties = ET.SubElement(order_info, "PARTIES")
    buyer_party = ET.SubElement(parties, "PARTY")
    ET.SubElement(buyer_party, "PARTY_ROLE").text = "buyer"
    ET.SubElement(buyer_party, "PARTY_ID", {"type": "buyer_specific"}).text = customer_id
    
    address = ET.SubElement(buyer_party, "ADDRESS")
    ET.SubElement(address, "NAME").text = customer_name

    # 2. ORDER_ITEM_LIST
    item_list = ET.SubElement(root, "ORDER_ITEM_LIST")
    for idx, item in enumerate(line_items, start=1):
        order_item = ET.SubElement(item_list, "ORDER_ITEM")
        ET.SubElement(order_item, "LINE_ITEM_ID").text = str(item.get("line_number", idx))

        article_id = ET.SubElement(order_item, "ARTICLE_ID")
        ET.SubElement(article_id, "SUPPLIER_AID").text = item.get("matched_sku", "UNKNOWN")
        ET.SubElement(article_id, "DESCRIPTION_SHORT").text = item.get("title_de", item.get("raw_description", ""))

        ET.SubElement(order_item, "QUANTITY").text = f"{float(item.get('base_quantity', 1.0)):.2f}"
        ET.SubElement(order_item, "ORDER_UNIT").text = item.get("base_uom", "C62")  # C62 is UN/ECE code for Piece/Stück

        price_elem = ET.SubElement(order_item, "ARTICLE_PRICE")
        ET.SubElement(price_elem, "PRICE_AMOUNT").text = f"{float(item.get('unit_price_net', 0.0)):.2f}"
        ET.SubElement(price_elem, "PRICE_LINE_AMOUNT").text = f"{float(item.get('total_price_net', 0.0)):.2f}"
        ET.SubElement(price_elem, "TAX").text = f"{float(item.get('tax_rate', 19.0)):.2f}"

    # 3. ORDER_SUMMARY
    summary = ET.SubElement(root, "ORDER_SUMMARY")
    ET.SubElement(summary, "TOTAL_ITEM_NUM").text = str(len(line_items))
    ET.SubElement(summary, "TOTAL_AMOUNT").text = f"{total_net_amount:.2f}"

    # Pretty print XML
    raw_xml = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(raw_xml)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
