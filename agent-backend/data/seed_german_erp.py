"""
BetriebsPilot AI - German ERP Seed Data Generator
Populates PostgreSQL with realistic German Mittelstand Master Data (Customers, Catalog SKUs,
Packaging Units, ATP Inventory, Historical Orders) and indexes the catalog into Qdrant for
3-Tier Cascade Hybrid RAG.
"""

import os
import random
import logging
from typing import List, Dict, Any
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_german_erp")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "betriebspilot")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "betriebspilot_secret")
POSTGRES_DB = os.getenv("POSTGRES_DB", "betriebspilot_erp")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION_NAME", "german_erp_catalog")

PG_CONN_STR = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ------------------------------------------------------------------------------
# Master Catalog Definitions
# ------------------------------------------------------------------------------
CATEGORIES = {
    "Befestigungstechnik": [
        ("DIN 933 Sechskantschraube", ["M6x16", "M6x25", "M8x20", "M8x30", "M8x45", "M10x30", "M10x50", "M12x40", "M12x60", "M16x50"], ["8.8 verzinkt", "10.9 schwarz", "A2 Edelstahl"], "STK", "KTN", 100, 0.12, 1.45),
        ("DIN 912 Zylinderkopfschraube mit Innensechskant", ["M5x12", "M6x20", "M6x30", "M8x25", "M8x35", "M10x40", "M12x50"], ["8.8 blank", "8.8 verzinkt", "A4 Säurebeständig"], "STK", "KTN", 50, 0.18, 2.10),
        ("DIN 934 Sechskantmutter", ["M5", "M6", "M8", "M10", "M12", "M16", "M20"], ["Güte 8 verzinkt", "A2 Edelstahl"], "STK", "PAK", 100, 0.05, 0.40),
        ("DIN 125 Unterlegscheibe Form A", ["6.4", "8.4", "10.5", "13.0", "17.0"], ["Stahl verzinkt", "A2 Edelstahl"], "STK", "PAK", 200, 0.02, 0.15),
        ("DIN 985 Selbstsichernde Mutter mit Polyamidring", ["M6", "M8", "M10", "M12", "M16"], ["Güte 8 verzinkt"], "STK", "PAK", 50, 0.08, 0.65),
    ],
    "Dichtungstechnik": [
        ("O-Ring FKM 80 Shore A (Viton)", ["10x2.0 mm", "15x2.5 mm", "18x3.0 mm", "22x3.0 mm", "25x3.0 mm", "32x4.0 mm", "40x4.0 mm", "50x5.0 mm"], ["braun", "schwarz"], "STK", "DOS", 12, 1.20, 8.50),
        ("O-Ring NBR 70 Shore A", ["8x2.0 mm", "12x2.5 mm", "16x2.5 mm", "20x3.0 mm", "24x3.0 mm", "28x3.5 mm", "35x4.0 mm", "45x4.5 mm"], ["schwarz industriequalität"], "STK", "DOS", 20, 0.45, 3.20),
        ("Radial-Wellendichtring DIN 3760 Form A", ["20x35x7 mm", "25x42x7 mm", "30x47x7 mm", "35x52x7 mm", "40x62x8 mm"], ["NBR / Carbonstahlfeder"], "STK", "STK", 1, 3.80, 12.00),
        ("Flachdichtung EPDM Trinkwasserzulassung", ["DN 15", "DN 20", "DN 25", "DN 32", "DN 40", "DN 50"], ["1.5 mm Stärke", "3.0 mm Stärke"], "STK", "PAK", 10, 0.95, 4.20),
    ],
    "Wälzlager": [
        ("Rillenkugellager einreihig DIN 625", ["6000-2RS", "6004-2RSH", "6201-ZZ", "6203-2RS", "6204-2RS1", "6205-2RS", "6302-2RSR", "6305-2RS"], ["Stahlblechkäfig C3"], "STK", "STK", 1, 4.20, 24.50),
        ("Kegelrollenlager DIN 720", ["30204", "30206", "32008-X", "32205"], ["Präzisionsausführung"], "STK", "STK", 1, 14.50, 48.00),
        ("Gehäuselager Stehlager UCP", ["UCP 204", "UCP 205", "UCP 206", "UCP 207"], ["Graugussgehäuse"], "STK", "STK", 1, 11.20, 32.00),
    ],
    "Pneumatik & Hydraulik": [
        ("Pneumatik-Schlauch Polyurethan (PUN)", ["PUN-4x0.75", "PUN-6x1.0", "PUN-8x1.25", "PUN-10x1.5", "PUN-12x2.0"], ["blau", "schwarz", "silber"], "MTR", "RLL", 50, 0.40, 1.80),
        ("Steckverschraubung gerade G-Gewinde", ["QS-G1/8-6", "QS-G1/4-8", "QS-G3/8-10", "QS-G1/2-12"], ["Messing vernickelt"], "STK", "PAK", 10, 1.85, 4.60),
        ("5/2-Wege Magnetventil federrückgestellt", ["1/8 Zoll 24V DC", "1/4 Zoll 24V DC", "1/4 Zoll 230V AC"], ["mit Handhilfsbetätigung"], "STK", "STK", 1, 38.00, 89.00),
        ("Drosselrückschlagventil Zuluft", ["G1/8 auf 6mm Schlauch", "G1/4 auf 8mm Schlauch"], ["Schwenkanschluss"], "STK", "STK", 1, 7.50, 16.00),
    ],
    "Elektromechanik": [
        ("WAGO Compact-Verbindungsklemme Serie 221", ["221-412 (2-Leiter)", "221-413 (3-Leiter)", "221-415 (5-Leiter)"], ["transparent mit Hebel 0.2-4.0 mm²"], "STK", "KTN", 100, 0.28, 0.65),
        ("M12 Sensor-Aktor-Kabel 4-polig", ["2.0 m PUR gerade", "5.0 m PUR gerade", "5.0 m PUR gewinkelt", "10.0 m PUR gerade"], ["ungeschirmt IP67"], "STK", "STK", 1, 6.80, 19.50),
        ("Kabelverschraubung Messing vernickelt metrisch", ["M16x1.5", "M20x1.5", "M25x1.5", "M32x1.5"], ["inkl. Gegenmutter IP68"], "STK", "PAK", 25, 1.40, 5.20),
    ]
}

CUSTOMERS = [
    {
        "customer_id": "DE-10021",
        "company_name": "Müller Maschinenbau GmbH & Co. KG",
        "vat_id": "DE143589211",
        "billing_email": "rechnung@mueller-maschinenbau.de",
        "street": "Industriestraße 42",
        "zip_code": "70565",
        "city": "Stuttgart",
        "sku_prefix": "MM"
    },
    {
        "customer_id": "DE-10022",
        "company_name": "Schmidt & Söhne Fördertechnik OHG",
        "vat_id": "DE812349001",
        "billing_email": "einkauf@schmidt-foerdertechnik.com",
        "street": "Hafenpromenade 12",
        "zip_code": "44147",
        "city": "Dortmund",
        "sku_prefix": "SCH"
    },
    {
        "customer_id": "DE-10023",
        "company_name": "Bayerische Feinmechanik Werkstätten AG",
        "vat_id": "DE129847113",
        "billing_email": "invoicing@bfm-augsburg.de",
        "street": "Dieselstraße 8",
        "zip_code": "86153",
        "city": "Augsburg",
        "sku_prefix": "BFM"
    },
    {
        "customer_id": "DE-10024",
        "company_name": "Hanseatische Schiffswerft & Zulieferer GmbH",
        "vat_id": "DE201994821",
        "billing_email": "finance@hsw-hamburg.de",
        "street": "Kanalstraße 101",
        "zip_code": "20457",
        "city": "Hamburg",
        "sku_prefix": "HSW"
    },
    {
        "customer_id": "DE-10025",
        "company_name": "Krupp & Becker Sondermaschinenbau KG",
        "vat_id": "DE119827364",
        "billing_email": "buchhaltung@krupp-becker.de",
        "street": "Glückauf-Ring 15",
        "zip_code": "45127",
        "city": "Essen",
        "sku_prefix": "KB"
    },
    {
        "customer_id": "DE-10026",
        "company_name": "Sachsen Pneumatik & Montagebau e.K.",
        "vat_id": "DE304918274",
        "billing_email": "service@sachsen-pneumatik.de",
        "street": "Dresdner Straße 88",
        "zip_code": "01067",
        "city": "Dresden",
        "sku_prefix": "SPM"
    },
    {
        "customer_id": "DE-10027",
        "company_name": "Baden Präzisionsdreherei GmbH",
        "vat_id": "DE289381745",
        "billing_email": "rechnungen@baden-praezision.de",
        "street": "Rheinstraße 14",
        "zip_code": "76133",
        "city": "Karlsruhe",
        "sku_prefix": "BPD"
    },
    {
        "customer_id": "DE-10028",
        "company_name": "Hessen Filter- und Dichtungssysteme GmbH",
        "vat_id": "DE114829103",
        "billing_email": "ap@hessen-filter.de",
        "street": "Hanauer Landstraße 210",
        "zip_code": "60314",
        "city": "Frankfurt am Main",
        "sku_prefix": "HFD"
    },
    {
        "customer_id": "DE-10029",
        "company_name": "Norddeutsche Industrieventilatoren GmbH",
        "vat_id": "DE249102847",
        "billing_email": "einkauf@nordvent-bremen.de",
        "street": "Weserufer 3",
        "zip_code": "28195",
        "city": "Bremen",
        "sku_prefix": "NIV"
    },
    {
        "customer_id": "DE-10030",
        "company_name": "Alpen Industrietechnik & Montagebedarf GmbH",
        "vat_id": "DE318274910",
        "billing_email": "fibu@alpen-industrietechnik.de",
        "street": "Allgäuer Weg 7",
        "zip_code": "87435",
        "city": "Kempten",
        "sku_prefix": "AIM"
    }
]

# ------------------------------------------------------------------------------
# Database Setup
# ------------------------------------------------------------------------------
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS erp_customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    vat_id VARCHAR(32) NOT NULL,
    billing_email VARCHAR(255) NOT NULL,
    street VARCHAR(255) NOT NULL,
    zip_code VARCHAR(16) NOT NULL,
    city VARCHAR(100) NOT NULL,
    payment_terms_days INT DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS erp_articles (
    sku VARCHAR(64) PRIMARY KEY,
    title_de VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL,
    specifications TEXT,
    base_uom VARCHAR(16) NOT NULL DEFAULT 'STK',
    packaging_unit VARCHAR(16) NOT NULL DEFAULT 'STK',
    packaging_qty INT NOT NULL DEFAULT 1,
    unit_price_net NUMERIC(10, 2) NOT NULL,
    tax_rate NUMERIC(5, 2) NOT NULL DEFAULT 19.00,
    min_reorder_level INT NOT NULL DEFAULT 50,
    lead_time_days INT NOT NULL DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS erp_inventory (
    sku VARCHAR(64) PRIMARY KEY REFERENCES erp_articles(sku) ON DELETE CASCADE,
    warehouse_id VARCHAR(32) NOT NULL DEFAULT 'WH-CENTRAL-01',
    physical_stock INT NOT NULL DEFAULT 0,
    reserved_stock INT NOT NULL DEFAULT 0,
    incoming_stock INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS erp_customer_sku_map (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL REFERENCES erp_customers(customer_id) ON DELETE CASCADE,
    raw_customer_sku VARCHAR(64) NOT NULL,
    matched_internal_sku VARCHAR(64) NOT NULL REFERENCES erp_articles(sku) ON DELETE CASCADE,
    confidence NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    source VARCHAR(32) NOT NULL DEFAULT 'HISTORICAL_IMPORT',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (customer_id, raw_customer_sku)
);

CREATE TABLE IF NOT EXISTS erp_orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL REFERENCES erp_customers(customer_id) ON DELETE CASCADE,
    channel VARCHAR(32) NOT NULL DEFAULT 'EMAIL',
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    total_net NUMERIC(12, 2) NOT NULL,
    total_gross NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS erp_order_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(32) NOT NULL REFERENCES erp_orders(order_id) ON DELETE CASCADE,
    sku VARCHAR(64) NOT NULL REFERENCES erp_articles(sku),
    raw_description VARCHAR(255),
    ordered_uom VARCHAR(16) NOT NULL,
    quantity INT NOT NULL,
    unit_price_net NUMERIC(10, 2) NOT NULL,
    total_price_net NUMERIC(10, 2) NOT NULL
);
"""

def generate_articles() -> List[Dict[str, Any]]:
    """Generates realistic German industrial articles based on DIN/ISO standards."""
    articles = []
    item_counter = 1000

    for category, product_types in CATEGORIES.items():
        for base_name, sizes, variants, base_uom, pkg_unit, pkg_qty, price_min, price_max in product_types:
            for size in sizes:
                for variant in variants:
                    item_counter += 1
                    # Clean SKU code
                    clean_name = base_name.split()[0].replace(" ", "-").upper()
                    clean_size = size.split()[0].replace(".", "_").replace("x", "X").upper()
                    clean_var = variant.split()[0].replace(".", "").upper()
                    sku = f"ART-{clean_name}-{clean_size}-{clean_var}-{item_counter:04d}"

                    title_de = f"{base_name} {size} ({variant})"
                    unit_price = round(Decimal(str(random.uniform(price_min, price_max))), 2)

                    articles.append({
                        "sku": sku,
                        "title_de": title_de,
                        "category": category,
                        "specifications": f"Abmessung: {size}, Spezifikation: {variant}, Norm: {base_name}",
                        "base_uom": base_uom,
                        "packaging_unit": pkg_unit,
                        "packaging_qty": pkg_qty,
                        "unit_price_net": unit_price,
                        "tax_rate": Decimal("19.00"),
                        "min_reorder_level": random.choice([25, 50, 100, 250]),
                        "lead_time_days": random.choice([2, 3, 5, 10])
                    })
    return articles

def seed_database():
    """Initializes schema and seeds PostgreSQL with customers, articles, stock & historical orders."""
    logger.info(f"Connecting to PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}...")
    with psycopg.connect(PG_CONN_STR) as conn:
        with conn.cursor() as cur:
            # 1. Initialize Tables
            logger.info("Executing DDL schema creation...")
            cur.execute(CREATE_TABLES_SQL)

            # 2. Insert Customers
            logger.info(f"Inserting {len(CUSTOMERS)} customers...")
            for cust in CUSTOMERS:
                cur.execute("""
                    INSERT INTO erp_customers (customer_id, company_name, vat_id, billing_email, street, zip_code, city)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (customer_id) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        billing_email = EXCLUDED.billing_email;
                """, (
                    cust["customer_id"], cust["company_name"], cust["vat_id"],
                    cust["billing_email"], cust["street"], cust["zip_code"], cust["city"]
                ))

            # 3. Generate & Insert Articles
            articles = generate_articles()
            logger.info(f"Generated {len(articles)} unique German industrial articles.")
            for art in articles:
                cur.execute("""
                    INSERT INTO erp_articles (
                        sku, title_de, category, specifications, base_uom, packaging_unit,
                        packaging_qty, unit_price_net, tax_rate, min_reorder_level, lead_time_days
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sku) DO UPDATE SET
                        title_de = EXCLUDED.title_de,
                        unit_price_net = EXCLUDED.unit_price_net;
                """, (
                    art["sku"], art["title_de"], art["category"], art["specifications"],
                    art["base_uom"], art["packaging_unit"], art["packaging_qty"],
                    art["unit_price_net"], art["tax_rate"], art["min_reorder_level"],
                    art["lead_time_days"]
                ))

                # Insert Inventory (Physical Stock, Reserved, Incoming)
                phys_stock = random.randint(20, 1500)
                reserved = random.randint(0, int(phys_stock * 0.3))
                incoming = random.choice([0, 50, 100, 200, 500])
                cur.execute("""
                    INSERT INTO erp_inventory (sku, warehouse_id, physical_stock, reserved_stock, incoming_stock)
                    VALUES (%s, 'WH-CENTRAL-01', %s, %s, %s)
                    ON CONFLICT (sku) DO UPDATE SET
                        physical_stock = EXCLUDED.physical_stock,
                        reserved_stock = EXCLUDED.reserved_stock,
                        incoming_stock = EXCLUDED.incoming_stock;
                """, (art["sku"], phys_stock, reserved, incoming))

            # 4. Create Customer SKU Cross-Reference Mappings (Tier 1 Cascade)
            logger.info("Generating Tier 1 Customer-to-Internal SKU cross references...")
            for cust in CUSTOMERS:
                prefix = cust["sku_prefix"]
                # Give each customer 8-15 mapped SKUs
                mapped_sample = random.sample(articles, k=random.randint(8, 15))
                for art in mapped_sample:
                    cust_sku = f"{prefix}-{art['sku'].split('-')[1]}-{random.randint(100, 999)}"
                    cur.execute("""
                        INSERT INTO erp_customer_sku_map (customer_id, raw_customer_sku, matched_internal_sku, confidence, source)
                        VALUES (%s, %s, %s, 1.00, 'HISTORICAL_IMPORT')
                        ON CONFLICT (customer_id, raw_customer_sku) DO NOTHING;
                    """, (cust["customer_id"], cust_sku, art["sku"]))

            # 5. Create Historical Orders (Tier 2 Context)
            logger.info("Generating past 24-month order history for each customer...")
            order_counter = 50000
            for cust in CUSTOMERS:
                for _ in range(random.randint(4, 8)):
                    order_counter += 1
                    order_id = f"AUF-2024-{order_counter}"
                    order_items = random.sample(articles, k=random.randint(2, 5))
                    
                    total_net = Decimal("0.00")
                    cur.execute("""
                        INSERT INTO erp_orders (order_id, customer_id, channel, status, total_net, total_gross)
                        VALUES (%s, %s, 'EMAIL', 'COMPLETED', 0.00, 0.00)
                        ON CONFLICT (order_id) DO NOTHING;
                    """, (order_id, cust["customer_id"]))

                    for art in order_items:
                        qty = random.choice([1, 2, 5, 10, 20]) * art["packaging_qty"]
                        item_total = Decimal(str(qty)) * art["unit_price_net"]
                        total_net += item_total

                        cur.execute("""
                            INSERT INTO erp_order_items (order_id, sku, raw_description, ordered_uom, quantity, unit_price_net, total_price_net)
                            VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """, (order_id, art["sku"], art["title_de"], art["base_uom"], qty, art["unit_price_net"], item_total))

                    total_gross = round(total_net * Decimal("1.19"), 2)
                    cur.execute("""
                        UPDATE erp_orders SET total_net = %s, total_gross = %s WHERE order_id = %s;
                    """, (total_net, total_gross, order_id))

        conn.commit()
    logger.info("✅ PostgreSQL database seeding successfully completed.")
    return articles

def index_qdrant_catalog(articles: List[Dict[str, Any]]):
    """Indexes catalog into Qdrant using FastEmbed for local vector search."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels
        from fastembed import TextEmbedding
    except ImportError:
        logger.warning("qdrant_client or fastembed not yet installed in active Python environment. Skipping Qdrant indexing.")
        return

    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Initialize FastEmbed model (BAAI/bge-small-en-v1.5 has 384 dimensions and fast CPU/GPU inference)
    embedding_model_name = "BAAI/bge-small-en-v1.5"
    logger.info(f"Loading FastEmbed model: {embedding_model_name}...")
    embedder = TextEmbedding(model_name=embedding_model_name)

    # Recreate Collection
    logger.info(f"Recreating Qdrant collection: {QDRANT_COLLECTION}...")
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE)
    )

    # Generate documents to embed: f"{title_de} | {category} | {sku} | {specifications}"
    texts = [
        f"{art['title_de']} | Kategorie: {art['category']} | Art-Nr: {art['sku']} | {art['specifications']}"
        for art in articles
    ]
    logger.info(f"Generating embeddings for {len(texts)} articles...")
    embeddings = list(embedder.embed(texts))

    # Upload to Qdrant in batches
    points = [
        qmodels.PointStruct(
            id=idx,
            vector=embedding.tolist(),
            payload={
                "sku": art["sku"],
                "title_de": art["title_de"],
                "category": art["category"],
                "specifications": art["specifications"],
                "base_uom": art["base_uom"],
                "packaging_unit": art["packaging_unit"],
                "packaging_qty": art["packaging_qty"],
                "unit_price_net": float(art["unit_price_net"]),
                "tax_rate": float(art["tax_rate"])
            }
        )
        for idx, (art, embedding) in enumerate(zip(articles, embeddings))
    ]

    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points[i:i + batch_size]
        )
    logger.info(f"✅ Successfully indexed {len(points)} articles into Qdrant collection '{QDRANT_COLLECTION}'.")

if __name__ == "__main__":
    seeded_articles = seed_database()
    index_qdrant_catalog(seeded_articles)
