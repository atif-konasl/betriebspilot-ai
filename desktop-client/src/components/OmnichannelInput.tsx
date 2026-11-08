import React, { useState, useEffect } from 'react';
import { Mail, FileText, MessageSquare, Upload, Zap, Building2, FileCheck } from 'lucide-react';
import { CustomerSummary } from '../types/erp';
import { agentClient } from '../api/agentClient';

interface OmnichannelInputProps {
  onProcess: (formData: FormData, customerId: string, channel: string, rawText: string) => void;
  isProcessing: boolean;
}

const PRESET_TEMPLATES = [
  {
    name: 'Müller Maschinenbau (Schrauben & O-Ringe)',
    customerId: 'DE-10021',
    channel: 'email',
    content: `Guten Morgen Herr Weber,

wir benötigen für unser Werk Stuttgart dringend folgende Teile aus dem Rahmenvertrag:

Pos 1: 10 Kartons von den Sechskantschrauben M8x30 verzinkt Güte 8.8
Pos 2: 5 Dosen O-Ring Dichtungen (unsere Teilenummer MM-O-687)
Pos 3: 20 Stück Rillenkugellager 6302-2RSR (wie im letzten Auftrag bestellt)

Bestellnummer: PO-STGT-2026-8812
Liefertermin: bis spätestens Freitag!

Mit freundlichen Grüßen,
Markus Schmidt
Müller Maschinenbau GmbH & Co. KG`,
  },
  {
    name: 'Wagner Armaturen (Vage Anfrage O-Ringe)',
    customerId: 'DE-10023',
    channel: 'email',
    content: `Hallo BetriebsPilot Team,

bitte liefern Sie uns 100 Stück FKM O-Ringe 22x3 braun aus dem Angebot vom März.
Zusätzlich benötigen wir 5 Kartons Zylinderschrauben M6x20 verzinkt.

Kunden-Auftragsnummer: WA-PO-4491-X
Bitte schnellstmöglich versenden.

Beste Grüße,
Wagner Armaturen GmbH`,
  },
  {
    name: 'WhatsApp Baustellen-Eildienst',
    customerId: 'DE-10021',
    channel: 'whatsapp',
    content: `[14:20, 08.11.2026] Markus Schmidt: Hallo, brauchen dringend 2 Kartons M8x30 Sechskantschrauben auf die Baustelle! Bestell-Nr PO-WA-091`,
  },
];

export const OmnichannelInput: React.FC<OmnichannelInputProps> = ({
  onProcess,
  isProcessing,
}) => {
  const [channel, setChannel] = useState<'email' | 'pdf' | 'whatsapp'>('email');
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('DE-10021');
  const [rawText, setRawText] = useState<string>(PRESET_TEMPLATES[0].content);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Load customer directory on mount
  useEffect(() => {
    agentClient
      .getCustomers()
      .then((data) => {
        setCustomers(data);
      })
      .catch((err) => console.error('Failed to load customers', err));
  }, []);

  const handleApplyTemplate = (template: (typeof PRESET_TEMPLATES)[0]) => {
    setSelectedCustomerId(template.customerId);
    setChannel(template.channel as any);
    setRawText(template.content);
    setSelectedFile(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setRawText(`[PDF-Datei ausgewählt: ${file.name} (${(file.size / 1024).toFixed(1)} KB)]`);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('customer_id', selectedCustomerId);
    formData.append('channel', channel);

    if (channel === 'pdf' && selectedFile) {
      formData.append('file', selectedFile);
    } else {
      formData.append('raw_text', rawText);
    }

    onProcess(formData, selectedCustomerId, channel, rawText);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-full shadow-lg">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
        <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
          <Upload className="w-4 h-4 text-sky-400" />
          1. Omnichannel Auftragseingang
        </h2>
        <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
          Inbound Queue
        </span>
      </div>

      {/* Customer Selection */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-400 mb-1 flex items-center gap-1.5">
          <Building2 className="w-3.5 h-3.5 text-slate-400" />
          ERP-Kunde (Mittelstand Zulieferer)
        </label>
        <select
          value={selectedCustomerId}
          onChange={(e) => setSelectedCustomerId(e.target.value)}
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
        >
          {customers.map((c) => (
            <option key={c.customer_id} value={c.customer_id}>
              {c.customer_id} — {c.company_name} ({c.city})
            </option>
          ))}
          {customers.length === 0 && (
            <option value="DE-10021">DE-10021 — Müller Maschinenbau GmbH & Co. KG (Stuttgart)</option>
          )}
        </select>
      </div>

      {/* Channel Tabs */}
      <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 mb-3 text-xs">
        <button
          type="button"
          onClick={() => setChannel('email')}
          className={`flex-1 py-1.5 rounded flex items-center justify-center gap-1.5 font-medium transition ${
            channel === 'email'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Mail className="w-3.5 h-3.5" /> E-Mail
        </button>
        <button
          type="button"
          onClick={() => setChannel('pdf')}
          className={`flex-1 py-1.5 rounded flex items-center justify-center gap-1.5 font-medium transition ${
            channel === 'pdf'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-3.5 h-3.5" /> PDF-Anhang
        </button>
        <button
          type="button"
          onClick={() => setChannel('whatsapp')}
          className={`flex-1 py-1.5 rounded flex items-center justify-center gap-1.5 font-medium transition ${
            channel === 'whatsapp'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" /> WhatsApp / SMS
        </button>
      </div>

      {/* Quick B2B Demo Templates */}
      <div className="mb-3">
        <div className="text-[11px] text-slate-400 mb-1.5 font-medium">Beispiel-Aufträge (1-Click Test):</div>
        <div className="flex flex-col gap-1">
          {PRESET_TEMPLATES.map((tmpl) => (
            <button
              key={tmpl.name}
              type="button"
              onClick={() => handleApplyTemplate(tmpl)}
              className="text-left text-xs bg-slate-950/70 hover:bg-slate-800 text-slate-300 hover:text-white px-2.5 py-1 rounded border border-slate-800/80 transition flex items-center justify-between"
            >
              <span className="truncate">{tmpl.name}</span>
              <FileCheck className="w-3 h-3 text-sky-400 shrink-0 ml-1" />
            </button>
          ))}
        </div>
      </div>

      {/* Input Field: Text Area or File Dropzone */}
      <div className="flex-1 flex flex-col mb-4">
        {channel === 'pdf' ? (
          <div className="flex-1 border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-lg p-6 flex flex-col items-center justify-center text-center bg-slate-950/40 cursor-pointer transition relative">
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />
            <FileText className="w-8 h-8 text-sky-400 mb-2" />
            <div className="text-xs font-medium text-slate-200 mb-1">
              {selectedFile ? selectedFile.name : 'PDF-Bestellung hier ablegen'}
            </div>
            <div className="text-[11px] text-slate-500">
              {selectedFile
                ? `${(selectedFile.size / 1024).toFixed(1)} KB ausgewählt`
                : 'oder klicken zum Auswählen'}
            </div>
          </div>
        ) : (
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Unstrukturierten deutschen Bestelltext hier einfügen..."
            rows={10}
            className="w-full flex-1 bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs text-slate-200 font-mono placeholder-slate-600 focus:outline-none focus:border-sky-500 resize-none leading-relaxed"
          />
        )}
      </div>

      {/* Submit Action */}
      <button
        onClick={handleSubmit}
        disabled={isProcessing || (!rawText.trim() && !selectedFile)}
        className="w-full bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 px-4 rounded-lg text-xs flex items-center justify-center gap-2 shadow-md transition"
      >
        <Zap className="w-4 h-4" />
        {isProcessing ? 'Agent verarbeitet Auftrag...' : 'Auftrag analysieren & extrahieren'}
      </button>
    </div>
  );
};
