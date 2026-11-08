import React, { useState } from 'react';
import {
  FileText,
  Search,
  CheckCircle2,
  AlertTriangle,
  Package,
  Layers,
  ShieldAlert
} from 'lucide-react';
import { ResolvedLineItem, InventoryCheckResult, CatalogSearchResult } from '../types/erp';
import { CatalogSearchModal } from './CatalogSearchModal';

interface SplitScreenReviewProps {
  rawText: string;
  items: ResolvedLineItem[];
  inventoryChecks: InventoryCheckResult[];
  overallConfidence: number;
  requiresReview: boolean;
  reviewReasons: string[];
  onUpdateItem: (index: number, updated: ResolvedLineItem) => void;
}

export const SplitScreenReview: React.FC<SplitScreenReviewProps> = ({
  rawText,
  items,
  inventoryChecks,
  overallConfidence,
  requiresReview,
  reviewReasons,
  onUpdateItem,
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const handleOpenSearch = (index: number) => {
    setEditingIndex(index);
    setModalOpen(true);
  };

  const handleSelectSkuOverride = (searchResult: CatalogSearchResult) => {
    if (editingIndex === null) return;
    const current = items[editingIndex];
    const updated: ResolvedLineItem = {
      ...current,
      matched_sku: searchResult.sku,
      title_de: searchResult.title_de,
      unit_price_net: searchResult.unit_price_net,
      total_price_net: current.base_quantity * searchResult.unit_price_net,
      packaging_factor: searchResult.packaging_qty || 1,
      confidence_score: 1.0, // Human overridden
      resolution_tier: 'TIER_1_DIRECT_ALIAS',
      requires_review: false,
    };
    onUpdateItem(editingIndex, updated);
  };

  const getInventoryForSku = (sku: string): InventoryCheckResult | undefined => {
    return inventoryChecks.find((inv) => inv.sku === sku);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-full shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-sky-400" />
          <h2 className="text-sm font-semibold text-slate-100">
            2. Split-Screen Prüfung & Sachbearbeiter-Review
          </h2>
        </div>

        {/* Confidence & Review Status Badge */}
        <div className="flex items-center gap-2">
          <span
            className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full flex items-center gap-1 border ${
              requiresReview
                ? 'bg-amber-950/40 text-amber-300 border-amber-800/50'
                : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50'
            }`}
          >
            {requiresReview ? (
              <AlertTriangle className="w-3 h-3 text-amber-400" />
            ) : (
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            )}
            Konfidenz: {(overallConfidence * 100).toFixed(1)}%
          </span>

          {requiresReview && (
            <span className="text-[11px] bg-red-950/50 text-red-300 border border-red-800/50 px-2 py-0.5 rounded-full">
              Prüfung erforderlich
            </span>
          )}
        </div>
      </div>

      {/* Review Reasons Notification if triggered */}
      {requiresReview && reviewReasons.length > 0 && (
        <div className="mb-3 bg-amber-950/30 border border-amber-800/40 rounded-lg p-2.5 text-xs text-amber-200 flex items-start gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="font-semibold">Human-in-the-Loop Begründung:</span>
            <ul className="list-disc list-inside mt-0.5 text-amber-300/90 text-[11px] space-y-0.5">
              {reviewReasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Split-Screen Layout: Top = Source Doc, Bottom = Structured ERP Items */}
      <div className="flex-1 flex flex-col gap-3 min-h-0">
        {/* Source Document Card */}
        <div className="h-32 bg-slate-950 rounded-lg border border-slate-800 p-3 overflow-y-auto">
          <div className="text-[11px] font-semibold text-slate-400 mb-1 flex items-center gap-1.5 uppercase tracking-wider">
            <FileText className="w-3 h-3 text-slate-400" /> Original-Bestelltext des Kunden
          </div>
          <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed select-text">
            {rawText || 'Kein Belegtext geladen.'}
          </pre>
        </div>

        {/* Structured Line Items Table */}
        <div className="flex-1 flex flex-col bg-slate-950 rounded-lg border border-slate-800 overflow-hidden">
          <div className="px-3 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <Package className="w-3.5 h-3.5 text-sky-400" />
              Extrahierte ERP-Auftragspositionen ({items.length})
            </span>
            <span className="text-[11px] text-slate-400">
              Klick auf SKU öffnet semantische Katalogsuche
            </span>
          </div>

          <div className="flex-1 overflow-auto">
            {items.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs p-6">
                <Package className="w-8 h-8 mb-2 text-slate-600" />
                Noch keine Positionen extrahiert. Wähle links einen Auftrag und klicke "Auftrag analysieren".
              </div>
            ) : (
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-[11px] text-slate-400 bg-slate-900/40 uppercase tracking-wider sticky top-0">
                    <th className="py-2 px-3">Pos</th>
                    <th className="py-2 px-3">Interne ERP-SKU</th>
                    <th className="py-2 px-3">Artikelbezeichnung</th>
                    <th className="py-2 px-2 text-center">Tier</th>
                    <th className="py-2 px-3 text-right">Bestellt</th>
                    <th className="py-2 px-3 text-right">Basis-Menge</th>
                    <th className="py-2 px-3 text-right">Einzelpreis</th>
                    <th className="py-2 px-3 text-right">Netto Gesamt</th>
                    <th className="py-2 px-3 text-center">ATP-Bestand</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {items.map((item, index) => {
                    const inv = getInventoryForSku(item.matched_sku);
                    const isInStock = inv ? inv.is_in_stock : true;

                    return (
                      <tr
                        key={index}
                        className={`hover:bg-slate-800/40 transition group ${
                          item.requires_review ? 'bg-amber-950/10' : ''
                        }`}
                      >
                        {/* Pos */}
                        <td className="py-2 px-3 font-mono text-slate-400">{item.line_number}</td>

                        {/* Matched SKU with Override button */}
                        <td className="py-2 px-3">
                          <button
                            type="button"
                            onClick={() => handleOpenSearch(index)}
                            className="font-mono text-sky-400 hover:text-sky-300 font-medium bg-sky-950/40 hover:bg-sky-900/50 px-2 py-0.5 rounded border border-sky-800/40 flex items-center gap-1.5 transition text-left"
                            title="Klicken, um SKU im ERP-Katalog manuell zu suchen / überschreiben"
                          >
                            <span>{item.matched_sku}</span>
                            <Search className="w-3 h-3 text-sky-400 opacity-60 group-hover:opacity-100" />
                          </button>
                          {item.raw_item_number && (
                            <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                              Kunde: {item.raw_item_number}
                            </div>
                          )}
                        </td>

                        {/* German Title */}
                        <td className="py-2 px-3 text-slate-200 max-w-xs truncate" title={item.title_de}>
                          {item.title_de}
                        </td>

                        {/* Tier Badge */}
                        <td className="py-2 px-2 text-center">
                          {item.resolution_tier === 'TIER_1_DIRECT_ALIAS' && (
                            <span className="text-[10px] font-mono bg-emerald-950/50 text-emerald-400 border border-emerald-800/50 px-1.5 py-0.5 rounded">
                              T1 Alias
                            </span>
                          )}
                          {item.resolution_tier === 'TIER_2_ORDER_HISTORY' && (
                            <span className="text-[10px] font-mono bg-blue-950/50 text-blue-400 border border-blue-800/50 px-1.5 py-0.5 rounded">
                              T2 History
                            </span>
                          )}
                          {item.resolution_tier === 'TIER_3_QDRANT_HYBRID' && (
                            <span className="text-[10px] font-mono bg-amber-950/50 text-amber-400 border border-amber-800/50 px-1.5 py-0.5 rounded">
                              T3 Vector
                            </span>
                          )}
                          {item.resolution_tier === 'UNRESOLVED' && (
                            <span className="text-[10px] font-mono bg-red-950/50 text-red-400 border border-red-800/50 px-1.5 py-0.5 rounded">
                              Offen
                            </span>
                          )}
                        </td>

                        {/* Ordered Qty */}
                        <td className="py-2 px-3 text-right text-slate-300 font-mono">
                          {item.ordered_quantity} {item.ordered_uom}
                        </td>

                        {/* Base Quantity (Calculated via Packaging Math) */}
                        <td className="py-2 px-3 text-right">
                          <span className="font-mono font-medium text-slate-100">
                            {item.base_quantity} {item.base_uom}
                          </span>
                          {item.packaging_factor > 1 && (
                            <div className="text-[10px] text-slate-400">
                              (Faktor {item.packaging_factor})
                            </div>
                          )}
                        </td>

                        {/* Unit Price Net */}
                        <td className="py-2 px-3 text-right text-slate-300 font-mono">
                          {item.unit_price_net.toFixed(2)} €
                        </td>

                        {/* Total Net */}
                        <td className="py-2 px-3 text-right font-mono font-medium text-slate-100">
                          {item.total_price_net.toFixed(2)} €
                        </td>

                        {/* ATP Stock Availability */}
                        <td className="py-2 px-3 text-center">
                          {isInStock ? (
                            <span
                              className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded"
                              title={inv ? `Verfügbar: ${inv.atp_stock} STK` : 'Verfügbar'}
                            >
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" /> Auf Lager
                            </span>
                          ) : (
                            <span
                              className="inline-flex items-center gap-1 text-[10px] font-medium text-red-400 bg-red-950/40 border border-red-800/40 px-2 py-0.5 rounded"
                              title={inv ? `Fehlmenge: ${inv.shortage_quantity} STK` : 'Rückstand'}
                            >
                              <AlertTriangle className="w-3 h-3 text-red-400" /> Rückstand
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Semantic Vector Search Modal */}
      <CatalogSearchModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSelectSku={handleSelectSkuOverride}
        initialQuery={editingIndex !== null ? items[editingIndex]?.title_de || '' : ''}
        lineNumber={editingIndex !== null ? items[editingIndex]?.line_number : 1}
      />
    </div>
  );
};
