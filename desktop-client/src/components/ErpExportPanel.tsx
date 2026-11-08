import React, { useState } from 'react';
import {
  FileCode,
  FolderInput,
  CheckCircle2,
  Copy,
  Save,
  Loader2,
  Check,
  Code
} from 'lucide-react';
import {
  ResolvedLineItem,
  ApproveAndExportRequest,
  ApproveAndExportResponse
} from '../types/erp';
import { agentClient } from '../api/agentClient';
import { hotfolderService, ExportResult } from '../services/hotfolderService';

interface ErpExportPanelProps {
  taskId: string;
  customerId: string;
  items: ResolvedLineItem[];
  totalNet: number;
  totalGross: number;
  isProcessing: boolean;
  onExportSuccess: (res: ApproveAndExportResponse, exportRes: ExportResult) => void;
}

export const ErpExportPanel: React.FC<ErpExportPanelProps> = ({
  taskId,
  customerId,
  items,
  totalNet,
  totalGross,
  isProcessing,
  onExportSuccess,
}) => {
  const [exportFormat, setExportFormat] = useState<'opentrans_xml' | 'sap_b1_json'>('opentrans_xml');
  const [watchfolder, setWatchfolder] = useState<string>(hotfolderService.getDefaultFolder());
  const [learnAliases, setLearnAliases] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportResult, setExportResult] = useState<ApproveAndExportResponse | null>(null);
  const [fileWriteResult, setFileWriteResult] = useState<ExportResult | null>(null);
  const [showPayloadModal, setShowPayloadModal] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const vat19 = totalGross - totalNet;

  const handleApproveAndExport = async () => {
    if (!taskId || items.length === 0) return;

    setIsExporting(true);
    setExportResult(null);
    setFileWriteResult(null);

    try {
      const payload: ApproveAndExportRequest = {
        task_id: taskId,
        customer_id: customerId,
        customer_order_number: `PO-AUTO-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`,
        order_date: new Date().toISOString().slice(0, 10),
        delivery_date: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10),
        export_format: exportFormat,
        learn_aliases: learnAliases,
        approved_line_items: items.map((it) => ({
          line_number: it.line_number,
          raw_item_number: it.raw_item_number || null,
          matched_sku: it.matched_sku,
          title_de: it.title_de,
          base_quantity: it.base_quantity,
          base_uom: it.base_uom,
          unit_price_net: it.unit_price_net,
          total_price_net: it.total_price_net,
          tax_rate: it.tax_rate,
        })),
      };

      // 1. Call FastAPI backend for approval & XML/JSON generation
      const apiResponse = await agentClient.approveAndExport(payload);
      setExportResult(apiResponse);

      // 2. Write file to hotfolder
      const writeResult = await hotfolderService.exportFile(
        apiResponse.file_name,
        apiResponse.payload_content,
        watchfolder
      );
      setFileWriteResult(writeResult);

      onExportSuccess(apiResponse, writeResult);
    } catch (err: any) {
      console.error('Approve and export failed', err);
      alert(`Export fehlgeschlagen: ${err.message || String(err)}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleCopyPayload = () => {
    if (exportResult?.payload_content) {
      navigator.clipboard.writeText(exportResult.payload_content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-full shadow-lg">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
        <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
          <FolderInput className="w-4 h-4 text-sky-400" />
          3. ERP-Export & Hotfolder
        </h2>
        <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
          GoBD Konform
        </span>
      </div>

      {/* Format Selector */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-400 mb-1.5">
          Ziel-ERP Schnittstellenformat
        </label>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <button
            type="button"
            onClick={() => setExportFormat('opentrans_xml')}
            className={`p-2.5 rounded-lg border text-left transition ${
              exportFormat === 'opentrans_xml'
                ? 'bg-sky-950/50 border-sky-500 text-sky-200 ring-1 ring-sky-500/20'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <div className="font-semibold text-xs flex items-center gap-1.5">
              <FileCode className="w-3.5 h-3.5 text-sky-400" />
              OpenTRANS 2.1 XML
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Sage 100, proALPHA, abas ERP
            </div>
          </button>

          <button
            type="button"
            onClick={() => setExportFormat('sap_b1_json')}
            className={`p-2.5 rounded-lg border text-left transition ${
              exportFormat === 'sap_b1_json'
                ? 'bg-sky-950/50 border-sky-500 text-sky-200 ring-1 ring-sky-500/20'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <div className="font-semibold text-xs flex items-center gap-1.5">
              <FileCode className="w-3.5 h-3.5 text-blue-400" />
              SAP Business One JSON
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              B1 Service Layer API / DI-Server
            </div>
          </button>
        </div>
      </div>

      {/* Target Watchfolder Input */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-400 mb-1 flex items-center justify-between">
          <span>Lokaler ERP-Hotfolder Pfad</span>
          <span className="text-[10px] text-slate-500">Watched Directory</span>
        </label>
        <input
          type="text"
          value={watchfolder}
          onChange={(e) => setWatchfolder(e.target.value)}
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
          placeholder="/tmp/erp_import oder C:\ERP_Import"
        />
      </div>

      {/* GoBD Audit & Financial Summary */}
      <div className="bg-slate-950 rounded-lg border border-slate-800 p-3 mb-4 space-y-2 text-xs">
        <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider pb-1 border-b border-slate-800/80">
          GoBD Rechnungs- & Auftragssumme
        </div>
        <div className="flex justify-between text-slate-300">
          <span>Anzahl Positionen:</span>
          <span className="font-mono font-medium text-slate-100">{items.length}</span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span>Netto-Warenwert:</span>
          <span className="font-mono font-medium text-slate-100">{totalNet.toFixed(2)} €</span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span>19% MwSt. (USt):</span>
          <span className="font-mono font-medium text-slate-100">{vat19.toFixed(2)} €</span>
        </div>
        <div className="flex justify-between text-slate-100 pt-1.5 border-t border-slate-800 font-semibold text-sm">
          <span>Gesamtbetrag (Brutto):</span>
          <span className="font-mono text-sky-400">{totalGross.toFixed(2)} €</span>
        </div>
      </div>

      {/* Tier 1 Self-Learning Checkbox */}
      <div className="mb-4 flex items-start gap-2 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
        <input
          type="checkbox"
          id="learnAliases"
          checked={learnAliases}
          onChange={(e) => setLearnAliases(e.target.checked)}
          className="mt-0.5 rounded border-slate-700 text-sky-600 focus:ring-sky-500 bg-slate-900"
        />
        <label htmlFor="learnAliases" className="text-xs text-slate-300 cursor-pointer select-none">
          <span className="font-medium text-slate-200 block">Kunden-Artikelnummern lernen</span>
          <span className="text-[10px] text-slate-400">
            Speichert Sachbearbeiter-Korrekturen automatisch in Tier 1 Alias-Tabelle für 100% Trefferquote beim nächsten Mal.
          </span>
        </label>
      </div>

      {/* Export Result Card */}
      {fileWriteResult && (
        <div
          className={`mb-4 p-3 rounded-lg border text-xs ${
            fileWriteResult.success
              ? 'bg-emerald-950/30 border-emerald-800/50 text-emerald-200'
              : 'bg-red-950/30 border-red-800/50 text-red-200'
          }`}
        >
          <div className="flex items-center gap-1.5 font-semibold mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            {fileWriteResult.message}
          </div>
          {exportResult && (
            <div className="text-[11px] text-emerald-300/80 space-y-0.5">
              <div>Datei: <span className="font-mono text-emerald-200">{exportResult.file_name}</span></div>
              {exportResult.learned_alias_count > 0 && (
                <div>Gelernte Kunden-Aliase: {exportResult.learned_alias_count}</div>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={() => setShowPayloadModal(true)}
            className="mt-2 text-[11px] bg-slate-900 hover:bg-slate-800 text-slate-200 px-2.5 py-1 rounded border border-slate-700 flex items-center gap-1 transition"
          >
            <Code className="w-3 h-3 text-sky-400" /> XML / JSON Payload anzeigen
          </button>
        </div>
      )}

      {/* Action Button: 1-Click Approve and Export */}
      <button
        onClick={handleApproveAndExport}
        disabled={isExporting || isProcessing || items.length === 0}
        className="w-full mt-auto bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white font-semibold py-2.5 px-4 rounded-lg text-xs flex items-center justify-center gap-2 shadow-md transition"
      >
        {isExporting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Generiere ERP-Payload & schreibe Hotfolder...
          </>
        ) : (
          <>
            <Save className="w-4 h-4" />
            1-Click Freigabe & in ERP-Hotfolder schreiben
          </>
        )}
      </button>

      {/* Raw Payload Modal */}
      {showPayloadModal && exportResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-3xl rounded-xl shadow-2xl flex flex-col max-h-[85vh]">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
              <span className="font-mono text-xs font-semibold text-slate-200">
                {exportResult.file_name}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopyPayload}
                  className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-2.5 py-1 rounded flex items-center gap-1.5 transition"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  {copied ? 'Kopiert!' : 'In Zwischenablage'}
                </button>
                <button
                  onClick={() => setShowPayloadModal(false)}
                  className="text-slate-400 hover:text-slate-200 px-2 py-1"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="p-4 overflow-auto flex-1 bg-slate-950 font-mono text-[11px] text-slate-300 leading-relaxed whitespace-pre select-text">
              {exportResult.payload_content}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
