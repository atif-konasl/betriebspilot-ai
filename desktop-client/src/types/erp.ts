/**
 * BetriebsPilot AI - TypeScript Data Contracts
 * Corresponds 1:1 with FastAPI Pydantic models (agent-backend/src/api/schemas.py)
 */

export interface CustomerSummary {
  customer_id: string;
  company_name: string;
  city: string;
  vat_id: string;
  billing_email: string;
}

export type ResolutionTier =
  | 'TIER_1_DIRECT_ALIAS'
  | 'TIER_2_ORDER_HISTORY'
  | 'TIER_3_QDRANT_HYBRID'
  | 'UNRESOLVED';

export interface ResolvedLineItem {
  line_number: number;
  raw_item_number?: string | null;
  matched_sku: string;
  title_de: string;
  ordered_quantity: number;
  ordered_uom: string;
  packaging_factor: number;
  base_quantity: number;
  base_uom: string;
  unit_price_net: number;
  total_price_net: number;
  tax_rate: number;
  confidence_score: number;
  resolution_tier: ResolutionTier;
  requires_review: boolean;
  notes?: string;
}

export interface InventoryCheckResult {
  sku: string;
  title_de: string;
  required_quantity: number;
  physical_stock: number;
  reserved_stock: number;
  incoming_stock: number;
  atp_stock: number;
  is_in_stock: boolean;
  shortage_quantity: number;
}

export interface ProcessInputResponse {
  task_id: string;
  status: string;
  intent?: string;
  customer_id: string;
  channel: string;
  extracted_document?: any;
  resolved_items: ResolvedLineItem[];
  inventory_checks: InventoryCheckResult[];
  overall_confidence: number;
  total_net_amount: number;
  total_gross_amount: number;
  requires_human_review: boolean;
  review_reasons: string[];
  export_format: string;
  generated_export_payload?: string | null;
  execution_trace: string[];
}

export interface ApprovedLineItem {
  line_number: number;
  raw_item_number?: string | null;
  matched_sku: string;
  title_de: string;
  base_quantity: number;
  base_uom: string;
  unit_price_net: number;
  total_price_net: number;
  tax_rate: number;
}

export interface ApproveAndExportRequest {
  task_id: string;
  customer_id: string;
  customer_order_number?: string | null;
  order_date?: string | null;
  delivery_date?: string | null;
  export_format: 'opentrans_xml' | 'sap_b1_json';
  approved_line_items: ApprovedLineItem[];
  learn_aliases: boolean;
}

export interface ApproveAndExportResponse {
  task_id: string;
  customer_id: string;
  export_format: string;
  learned_alias_count: number;
  file_name: string;
  payload_content: string;
}

export interface CatalogSearchResult {
  sku: string;
  title_de: string;
  category: string;
  base_uom: string;
  packaging_unit: string;
  packaging_qty: number;
  unit_price_net: number;
  tax_rate: number;
  score: number;
}

export interface SystemHealth {
  status: string;
  database: { connected: boolean; engine?: string };
  qdrant: { connected: boolean; collections?: string[] };
  llm: { status: string; provider?: string; model?: string; reachable?: boolean };
}

export interface TraceEvent {
  node: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  description?: string;
  timestamp?: string;
}
