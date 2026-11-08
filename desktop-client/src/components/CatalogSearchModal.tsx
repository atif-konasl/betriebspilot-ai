import React, { useState } from 'react';
import { Search, X, Loader2, Check, Sparkles } from 'lucide-react';
import { agentClient } from '../api/agentClient';
import { CatalogSearchResult } from '../types/erp';

interface CatalogSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSku: (item: CatalogSearchResult) => void;
  initialQuery?: string;
  lineNumber?: number;
}

export const CatalogSearchModal: React.FC<CatalogSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectSku,
  initialQuery = '',
  lineNumber = 1,
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<CatalogSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  if (!isOpen) return null;

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    try {
      const data = await agentClient.searchCatalog(query, 6);
      setResults(data);
      setHasSearched(true);
    } catch (err) {
      console.error('Vector catalog search failed', err);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-2xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-sky-400" />
            <h3 className="font-semibold text-slate-100 text-sm">
              Qdrant Semantische Artikelsuche (Position {lineNumber})
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search Bar */}
        <div className="p-4 border-b border-slate-800 bg-slate-900">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Artikelbezeichnung, Norm oder Maße eingeben (z.B. DIN 933 M8x30 Edelstahl)..."
                className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                autoFocus
              />
            </div>
            <button
              type="submit"
              disabled={isSearching}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium px-4 py-2 rounded-lg text-sm flex items-center gap-2 transition"
            >
              {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Suchen'}
            </button>
          </form>
        </div>

        {/* Results List */}
        <div className="p-4 overflow-y-auto space-y-2 flex-1">
          {isSearching && (
            <div className="py-12 text-center text-slate-400 flex flex-col items-center gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-sky-400" />
              <span>Durchsuche 172 Artikel im ERP-Katalog via Qdrant Hybrid Search...</span>
            </div>
          )}

          {!isSearching && results.length === 0 && hasSearched && (
            <div className="py-12 text-center text-slate-500 text-sm">
              Keine passenden Artikel im ERP-Katalog gefunden. Bitte Suchbegriff anpassen.
            </div>
          )}

          {!isSearching &&
            results.map((item) => (
              <div
                key={item.sku}
                className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800/60 transition group"
              >
                <div className="min-w-0 pr-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs font-semibold text-sky-400 bg-sky-950/50 px-2 py-0.5 rounded border border-sky-800/40">
                      {item.sku}
                    </span>
                    <span className="text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                      {item.category}
                    </span>
                    <span className="text-[11px] text-emerald-400 font-mono">
                      Match: {(item.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-sm font-medium text-slate-200 truncate">{item.title_de}</div>
                  <div className="text-xs text-slate-400 mt-1 flex gap-3">
                    <span>
                      Verpackung: {item.packaging_unit} à {item.packaging_qty} {item.base_uom}
                    </span>
                    <span>•</span>
                    <span className="text-slate-300 font-medium">
                      Katalogpreis: {item.unit_price_net.toFixed(2)} € / {item.base_uom}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => {
                    onSelectSku(item);
                    onClose();
                  }}
                  className="bg-slate-800 group-hover:bg-sky-600 text-slate-200 group-hover:text-white px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition"
                >
                  <Check className="w-3.5 h-3.5" /> Übernehmen
                </button>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};
