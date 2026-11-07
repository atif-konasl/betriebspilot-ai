"""
BetriebsPilot AI - 3-Tier Cascade SKU Resolution Engine
Resolves messy customer order items through:
  Tier 1: Direct Customer SKU Alias Map (100% confidence)
  Tier 2: Past 24-Month Customer Order History (95% confidence)
  Tier 3: Qdrant Hybrid Vector Search over Master ERP Catalog
Includes deterministic packaging unit conversion math (Kartons -> STK).
"""

import os
import re
import logging
from typing import Optional, List, Tuple, Dict, Any

import psycopg
from psycopg.rows import dict_row
from qdrant_client import QdrantClient
from fastembed import TextEmbedding

from src.ingestion.schemas import ExtractedLineItem, RawExtractedDocument
from src.rag.schemas import ResolutionTier, ResolvedLineItem, ResolutionSummary

logger = logging.getLogger("betriebspilot.rag.retriever")

# ------------------------------------------------------------------------------
# Unit of Measure Normalization Mapping
# ------------------------------------------------------------------------------
UOM_SYNONYMS = {
    "STK": ["stk", "stück", "stueck", "st", "pcs", "piece", "pieces", "stk."],
    "KTN": ["karton", "kartons", "ktn", "ktns", "ctn", "box", "karton.", "ktn."],
    "PAK": ["paket", "pakete", "pak", "pk", "pkg", "packung", "packungen", "pck"],
    "DOS": ["dose", "dosen", "dos", "can", "dosen."],
    "RLL": ["rolle", "rollen", "rll", "roll"],
    "MTR": ["meter", "m", "mtr", "m."],
    "SET": ["set", "sets", "satz", "sätze"]
}

def normalize_uom(uom_str: Optional[str]) -> str:
    """Normalizes colloquial German packaging strings to standard ERP codes."""
    if not uom_str:
        return "STK"
    clean = uom_str.strip().lower()
    for standard_code, synonyms in UOM_SYNONYMS.items():
        if clean in synonyms:
            return standard_code
    return uom_str.strip().upper()


class ThreeTierCascadeResolver:
    """
    Orchestrates the 3-Tier Cascade resolution pipeline for German ERP orders.
    """

    def __init__(
        self,
        pg_conn_str: Optional[str] = None,
        qdrant_host: Optional[str] = None,
        qdrant_port: Optional[int] = None,
        qdrant_collection: Optional[str] = None,
        embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    ):
        # Database configuration
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "betriebspilot")
        password = os.getenv("POSTGRES_PASSWORD", "betriebspilot_secret")
        db = os.getenv("POSTGRES_DB", "betriebspilot_erp")
        self.pg_conn_str = pg_conn_str or f"postgresql://{user}:{password}@{host}:{port}/{db}"

        # Qdrant configuration
        self.qdrant_host = qdrant_host or os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(qdrant_port or os.getenv("QDRANT_PORT", "6333"))
        self.qdrant_collection = qdrant_collection or os.getenv("QDRANT_COLLECTION_NAME", "german_erp_catalog")

        self.qdrant_client = QdrantClient(
            host=self.qdrant_host,
            port=self.qdrant_port,
            check_compatibility=False
        )
        self.embedder = TextEmbedding(model_name=embedding_model_name)
        logger.info("Initialized ThreeTierCascadeResolver with PostgreSQL & Qdrant.")

    # --------------------------------------------------------------------------
    # Tier 1: Deterministic Customer SKU Alias Map
    # --------------------------------------------------------------------------
    def _query_tier_1_alias(self, customer_id: str, raw_sku: Optional[str], description: str) -> Optional[Dict[str, Any]]:
        """Checks erp_customer_sku_map for customer-specific part numbers."""
        candidate_skus = []
        if raw_sku:
            candidate_skus.append(raw_sku.strip())

        # Also regex extract any code-like tokens from description (e.g. MM-0830-VZ or SCH-102)
        extracted_codes = re.findall(r"\b[A-Za-z0-9]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?\b", description)
        candidate_skus.extend(extracted_codes)

        if not candidate_skus:
            return None

        sql = """
            SELECT m.matched_internal_sku, m.confidence, a.title_de, a.category,
                   a.base_uom, a.packaging_unit, a.packaging_qty, a.unit_price_net, a.tax_rate
            FROM erp_customer_sku_map m
            JOIN erp_articles a ON a.sku = m.matched_internal_sku
            WHERE m.customer_id = %s AND m.raw_customer_sku = ANY(%s)
            LIMIT 1;
        """
        with psycopg.connect(self.pg_conn_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (customer_id, candidate_skus))
                res = cur.fetchone()
                if res:
                    logger.info(f"Tier 1 Direct Alias Match: {candidate_skus} -> {res['matched_internal_sku']}")
                    return dict(res)
        return None

    # --------------------------------------------------------------------------
    # Tier 2: 24-Month Customer Order History
    # --------------------------------------------------------------------------
    def _query_tier_2_history(self, customer_id: str, description: str) -> Optional[Dict[str, Any]]:
        """Searches past purchase history for this customer."""
        # Extract keywords (min 3 chars)
        words = [w.strip() for w in re.split(r"[\s,;]+", description) if len(w.strip()) >= 3]
        if not words:
            return None

        # Build ILIKE search pattern over top keywords
        search_pattern = f"%{words[0]}%"

        sql = """
            SELECT i.sku as matched_internal_sku, a.title_de, a.category,
                   a.base_uom, a.packaging_unit, a.packaging_qty, a.unit_price_net, a.tax_rate,
                   COUNT(*) as purchase_frequency
            FROM erp_order_items i
            JOIN erp_orders o ON o.order_id = i.order_id
            JOIN erp_articles a ON a.sku = i.sku
            WHERE o.customer_id = %s
              AND (i.raw_description ILIKE %s OR a.title_de ILIKE %s)
            GROUP BY i.sku, a.title_de, a.category, a.base_uom, a.packaging_unit, a.packaging_qty, a.unit_price_net, a.tax_rate
            ORDER BY purchase_frequency DESC
            LIMIT 1;
        """
        with psycopg.connect(self.pg_conn_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (customer_id, search_pattern, search_pattern))
                res = cur.fetchone()
                if res:
                    logger.info(f"Tier 2 Historical Match: '{description}' -> {res['matched_internal_sku']} (bought {res['purchase_frequency']}x)")
                    return dict(res)
        return None

    # --------------------------------------------------------------------------
    # Tier 3: Qdrant Semantic Vector Search
    # --------------------------------------------------------------------------
    def _query_tier_3_qdrant(self, query_text: str) -> Optional[Tuple[Dict[str, Any], float]]:
        """Performs semantic vector search over the master catalog in Qdrant."""
        try:
            embeddings = list(self.embedder.embed([query_text]))
            if not embeddings:
                return None
            vector = embeddings[0].tolist()

            if hasattr(self.qdrant_client, "query_points"):
                response = self.qdrant_client.query_points(
                    collection_name=self.qdrant_collection,
                    query=vector,
                    limit=1
                )
                points = response.points
            else:
                points = self.qdrant_client.search(
                    collection_name=self.qdrant_collection,
                    query_vector=vector,
                    limit=1
                )

            if not points:
                return None

            top = points[0]
            score = float(top.score)
            payload = top.payload or {}

            matched_data = {
                "matched_internal_sku": payload.get("sku"),
                "title_de": payload.get("title_de"),
                "category": payload.get("category"),
                "base_uom": payload.get("base_uom", "STK"),
                "packaging_unit": payload.get("packaging_unit", "STK"),
                "packaging_qty": payload.get("packaging_qty", 1),
                "unit_price_net": payload.get("unit_price_net", 0.0),
                "tax_rate": payload.get("tax_rate", 19.0),
            }
            logger.info(f"Tier 3 Qdrant Match: '{query_text}' -> {matched_data['matched_internal_sku']} (Score: {score:.3f})")
            return matched_data, score

        except Exception as e:
            logger.error(f"Error querying Qdrant: {e}")
            return None

    # --------------------------------------------------------------------------
    # Deterministic Packaging Math
    # --------------------------------------------------------------------------
    def _calculate_packaging_math(
        self,
        ordered_qty: float,
        ordered_uom_raw: str,
        article_data: Dict[str, Any]
    ) -> Tuple[str, int, float, float, bool, Optional[str]]:
        """
        Executes deterministic packaging unit conversion math.
        Formula: Base Qty = Ordered Qty * Packaging Factor
        """
        base_uom = article_data.get("base_uom", "STK")
        catalog_pkg_unit = article_data.get("packaging_unit", "STK")
        catalog_pkg_qty = int(article_data.get("packaging_qty", 1))
        unit_price_net = float(article_data.get("unit_price_net", 0.0))

        norm_ordered_uom = normalize_uom(ordered_uom_raw)
        norm_catalog_pkg = normalize_uom(catalog_pkg_unit)
        norm_base_uom = normalize_uom(base_uom)

        requires_review = False
        review_reason = None
        factor = 1

        # Case 1: Customer ordered in packaging units (e.g. Karton, Paket, Dose)
        if norm_ordered_uom == norm_catalog_pkg and norm_ordered_uom != norm_base_uom:
            factor = catalog_pkg_qty

        # Case 2: Customer ordered in base unit (e.g. STK, MTR)
        elif norm_ordered_uom == norm_base_uom:
            factor = 1

        # Case 3: Customer ordered in an unexpected or unconfigured unit
        else:
            factor = 1
            requires_review = True
            review_reason = (
                f"Abweichende Verpackungseinheit '{ordered_uom_raw}'. "
                f"Katalog definiert Basis '{base_uom}' und VPE '{catalog_pkg_unit}' ({catalog_pkg_qty} {base_uom})."
            )

        base_quantity = ordered_qty * factor
        total_price_net = round(base_quantity * unit_price_net, 2)

        return base_uom, factor, base_quantity, total_price_net, requires_review, review_reason

    # --------------------------------------------------------------------------
    # Single Item Resolution
    # --------------------------------------------------------------------------
    def resolve_item(self, customer_id: str, item: ExtractedLineItem) -> ResolvedLineItem:
        """Resolves an individual extracted line item through the 3-Tier Cascade."""
        # 1. Tier 1: Direct Alias
        tier_1_match = self._query_tier_1_alias(
            customer_id=customer_id,
            raw_sku=item.raw_item_number,
            description=item.raw_description
        )
        if tier_1_match:
            tier = ResolutionTier.TIER_1_DIRECT_ALIAS
            confidence = 1.00
            data = tier_1_match

        else:
            # 2. Tier 2: 24-Month History
            tier_2_match = self._query_tier_2_history(
                customer_id=customer_id,
                description=item.raw_description
            )
            if tier_2_match:
                tier = ResolutionTier.TIER_2_ORDER_HISTORY
                confidence = 0.95
                data = tier_2_match

            else:
                # 3. Tier 3: Qdrant Hybrid Search
                query = f"{item.raw_description} {item.raw_item_number or ''}".strip()
                tier_3_match = self._query_tier_3_qdrant(query)

                if tier_3_match and tier_3_match[1] >= 0.50:
                    data, score = tier_3_match
                    tier = ResolutionTier.TIER_3_QDRANT_HYBRID
                    confidence = round(score, 3)
                else:
                    # Item could not be resolved in any tier
                    return ResolvedLineItem(
                        line_number=item.line_number,
                        raw_description=item.raw_description,
                        raw_item_number=item.raw_item_number,
                        matched_sku="UNRESOLVED",
                        title_de="Nicht im Artikelstamm gefunden",
                        category="Unbekannt",
                        resolution_tier=ResolutionTier.UNRESOLVED,
                        confidence=0.0,
                        ordered_quantity=item.quantity,
                        ordered_uom=item.raw_uom,
                        base_uom="STK",
                        packaging_factor=1,
                        base_quantity=item.quantity,
                        unit_price_net=0.0,
                        total_price_net=0.0,
                        tax_rate=19.0,
                        requires_human_review=True,
                        review_reason="Artikel konnte in keinem Tier des Katalogs gefunden werden."
                    )

        # Execute packaging math
        base_uom, factor, base_qty, total_price, pkg_review, pkg_reason = self._calculate_packaging_math(
            ordered_qty=item.quantity,
            ordered_uom_raw=item.raw_uom,
            article_data=data
        )

        # Flag for human review if confidence < 0.95 or packaging unit mismatch
        needs_review = pkg_review or (confidence < 0.95)
        review_reason = pkg_reason
        if not review_reason and confidence < 0.95:
            review_reason = f"Konfidenz ({confidence:.2f}) unter Schwellenwert 0.95 (Tier 3 Suche)."

        return ResolvedLineItem(
            line_number=item.line_number,
            raw_description=item.raw_description,
            raw_item_number=item.raw_item_number,
            matched_sku=data["matched_internal_sku"],
            title_de=data["title_de"],
            category=data["category"],
            resolution_tier=tier,
            confidence=confidence,
            ordered_quantity=item.quantity,
            ordered_uom=item.raw_uom,
            base_uom=base_uom,
            packaging_factor=factor,
            base_quantity=base_qty,
            unit_price_net=float(data["unit_price_net"]),
            total_price_net=total_price,
            tax_rate=float(data.get("tax_rate", 19.0)),
            requires_human_review=needs_review,
            review_reason=review_reason
        )

    # --------------------------------------------------------------------------
    # Whole Document Resolution
    # --------------------------------------------------------------------------
    def resolve_document(
        self,
        customer_id: str,
        document: RawExtractedDocument
    ) -> Tuple[List[ResolvedLineItem], ResolutionSummary]:
        """Resolves all line items in an extracted document and produces an audit summary."""
        resolved_items: List[ResolvedLineItem] = []

        tier_1_count = 0
        tier_2_count = 0
        tier_3_count = 0
        review_count = 0
        total_net = 0.0
        confidence_sum = 0.0

        for item in document.line_items:
            resolved = self.resolve_item(customer_id=customer_id, item=item)
            resolved_items.append(resolved)

            if resolved.resolution_tier == ResolutionTier.TIER_1_DIRECT_ALIAS:
                tier_1_count += 1
            elif resolved.resolution_tier == ResolutionTier.TIER_2_ORDER_HISTORY:
                tier_2_count += 1
            elif resolved.resolution_tier == ResolutionTier.TIER_3_QDRANT_HYBRID:
                tier_3_count += 1

            if resolved.requires_human_review:
                review_count += 1

            total_net += resolved.total_price_net
            confidence_sum += resolved.confidence

        total_items = len(resolved_items)
        avg_confidence = round(confidence_sum / total_items, 3) if total_items > 0 else 0.0
        total_gross = round(total_net * 1.19, 2)

        summary = ResolutionSummary(
            total_items=total_items,
            resolved_items=total_items - sum(1 for i in resolved_items if i.resolution_tier == ResolutionTier.UNRESOLVED),
            tier_1_matches=tier_1_count,
            tier_2_matches=tier_2_count,
            tier_3_matches=tier_3_count,
            items_needing_review=review_count,
            overall_confidence=avg_confidence,
            total_net_amount=round(total_net, 2),
            total_gross_amount=total_gross
        )

        return resolved_items, summary

    # --------------------------------------------------------------------------
    # Self-Learning Alias Loop
    # --------------------------------------------------------------------------
    def learn_customer_alias(self, customer_id: str, raw_customer_sku: str, internal_sku: str):
        """
        Self-learning function: When a clerk approves an override in the UI,
        persist the mapping to erp_customer_sku_map for 100% future accuracy.
        """
        sql = """
            INSERT INTO erp_customer_sku_map (customer_id, raw_customer_sku, matched_internal_sku, confidence, source)
            VALUES (%s, %s, %s, 1.00, 'MANUAL_APPROVED')
            ON CONFLICT (customer_id, raw_customer_sku)
            DO UPDATE SET matched_internal_sku = EXCLUDED.matched_internal_sku,
                          confidence = 1.00,
                          updated_at = CURRENT_TIMESTAMP;
        """
        with psycopg.connect(self.pg_conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (customer_id, raw_customer_sku, internal_sku))
            conn.commit()
        logger.info(f"Learned alias: Customer '{customer_id}' | '{raw_customer_sku}' -> '{internal_sku}'")
