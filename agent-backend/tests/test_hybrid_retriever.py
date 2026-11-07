"""
Unit and integration tests for the 3-Tier Cascade SKU Resolution Engine.
Tests Tier 1 (Alias Map), Tier 2 (Order History), Tier 3 (Qdrant Vector Search),
and Deterministic Packaging Math.
"""

import pytest
from src.ingestion.schemas import ExtractedLineItem, RawExtractedDocument, InputChannel
from src.rag.schemas import ResolutionTier, ResolvedLineItem, ResolutionSummary
from src.rag.hybrid_retriever import (
    ThreeTierCascadeResolver,
    normalize_uom
)


# ------------------------------------------------------------------------------
# 1. Unit Normalization Tests
# ------------------------------------------------------------------------------
def test_normalize_uom():
    assert normalize_uom("karton") == "KTN"
    assert normalize_uom("Kartons") == "KTN"
    assert normalize_uom("ktn.") == "KTN"
    assert normalize_uom("Dosen") == "DOS"
    assert normalize_uom("stück") == "STK"
    assert normalize_uom("stk") == "STK"
    assert normalize_uom("Pakete") == "PAK"
    assert normalize_uom("Rollen") == "RLL"
    assert normalize_uom("Meter") == "MTR"
    assert normalize_uom("Sonderkiste") == "SONDERKISTE"


# ------------------------------------------------------------------------------
# 2. Packaging Math Tests
# ------------------------------------------------------------------------------
def test_packaging_math_direct():
    resolver = ThreeTierCascadeResolver()
    
    article_data = {
        "base_uom": "STK",
        "packaging_unit": "KTN",
        "packaging_qty": 100,
        "unit_price_net": 0.25
    }

    # Case A: Ordered in packaging units (10 Kartons)
    base_uom, factor, base_qty, total_price, needs_rev, reason = resolver._calculate_packaging_math(
        ordered_qty=10.0,
        ordered_uom_raw="Kartons",
        article_data=article_data
    )
    assert factor == 100
    assert base_qty == 1000.0
    assert total_price == 250.0
    assert needs_rev is False

    # Case B: Ordered in base units (50 STK)
    base_uom, factor, base_qty, total_price, needs_rev, reason = resolver._calculate_packaging_math(
        ordered_qty=50.0,
        ordered_uom_raw="STK",
        article_data=article_data
    )
    assert factor == 1
    assert base_qty == 50.0
    assert total_price == 12.50
    assert needs_rev is False

    # Case C: Unknown unit (e.g. Palette)
    base_uom, factor, base_qty, total_price, needs_rev, reason = resolver._calculate_packaging_math(
        ordered_qty=2.0,
        ordered_uom_raw="Palette",
        article_data=article_data
    )
    assert factor == 1
    assert needs_rev is True
    assert "Abweichende Verpackungseinheit" in reason


# ------------------------------------------------------------------------------
# 3. Live 3-Tier Cascade Integration Tests (PostgreSQL + Qdrant)
# ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def resolver():
    return ThreeTierCascadeResolver()


def test_tier_1_direct_alias_resolution(resolver):
    """Customer DE-10021 has seeded alias 'MM-O-687' -> 'ART-O-RING-22X3_0-BRAUN-1087'."""
    item = ExtractedLineItem(
        line_number=1,
        raw_description="Dichtungsringe",
        raw_item_number="MM-O-687",
        quantity=5,
        raw_uom="Dosen"
    )

    resolved = resolver.resolve_item(customer_id="DE-10021", item=item)

    assert resolved.resolution_tier == ResolutionTier.TIER_1_DIRECT_ALIAS
    assert resolved.matched_sku == "ART-O-RING-22X3_0-BRAUN-1087"
    assert resolved.confidence == 1.00
    assert resolved.base_quantity > 0


def test_tier_2_order_history_resolution(resolver):
    """Customer DE-10021 historically ordered 'Flachdichtung EPDM Trinkwasserzulassung DN 50'."""
    item = ExtractedLineItem(
        line_number=1,
        raw_description="Flachdichtung EPDM wie immer",
        quantity=20,
        raw_uom="STK"
    )

    resolved = resolver.resolve_item(customer_id="DE-10021", item=item)

    assert resolved.resolution_tier == ResolutionTier.TIER_2_ORDER_HISTORY
    assert resolved.confidence == 0.95
    assert "FLACHDICHTUNG" in resolved.matched_sku


def test_tier_3_qdrant_semantic_resolution(resolver):
    """Customer DE-10030 ordering a screw never bought before -> routes to Qdrant."""
    item = ExtractedLineItem(
        line_number=1,
        raw_description="Sechskantschraube M8x30 Güte 8.8 verzinkt",
        quantity=10,
        raw_uom="Karton"
    )

    resolved = resolver.resolve_item(customer_id="DE-10030", item=item)

    assert resolved.resolution_tier in (ResolutionTier.TIER_3_QDRANT_HYBRID, ResolutionTier.TIER_2_ORDER_HISTORY)
    assert resolved.confidence >= 0.70
    assert "DIN" in resolved.matched_sku


def test_resolve_document_end_to_end(resolver):
    """Resolves an entire multi-item document and checks summary metrics."""
    doc = RawExtractedDocument(
        channel=InputChannel.EMAIL,
        line_items=[
            ExtractedLineItem(
                line_number=1,
                raw_description="O-Ring",
                raw_item_number="MM-O-687",
                quantity=2,
                raw_uom="Dosen"
            ),
            ExtractedLineItem(
                line_number=2,
                raw_description="Rillenkugellager 6302-2RSR",
                quantity=4,
                raw_uom="STK"
            )
        ]
    )

    items, summary = resolver.resolve_document(customer_id="DE-10021", document=doc)

    assert len(items) == 2
    assert summary.total_items == 2
    assert summary.resolved_items == 2
    assert summary.total_net_amount > 0
    assert summary.total_gross_amount == round(summary.total_net_amount * 1.19, 2)


def test_self_learning_alias_loop(resolver):
    """Verify that human corrections persist into Tier 1 for future 100% accuracy."""
    cust_id = "DE-10025"
    test_sku_alias = "KB-SPECIAL-TEST-771"
    target_internal_sku = "ART-O-RING-22X3_0-BRAUN-1087"

    # 1. Clerk approves override in UI -> persist alias
    resolver.learn_customer_alias(
        customer_id=cust_id,
        raw_customer_sku=test_sku_alias,
        internal_sku=target_internal_sku
    )

    # 2. Next time this customer orders with this alias, it hits Tier 1 with 1.00 confidence
    item = ExtractedLineItem(
        line_number=1,
        raw_description="Spezialdichtung",
        raw_item_number=test_sku_alias,
        quantity=1,
        raw_uom="STK"
    )

    resolved = resolver.resolve_item(customer_id=cust_id, item=item)
    assert resolved.resolution_tier == ResolutionTier.TIER_1_DIRECT_ALIAS
    assert resolved.matched_sku == target_internal_sku
    assert resolved.confidence == 1.00
