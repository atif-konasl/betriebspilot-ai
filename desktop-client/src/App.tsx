import React, { useState, useEffect } from 'react';
import {
  Boxes,
  Database,
  Cpu,
  RefreshCw,
  Terminal
} from 'lucide-react';
import { OmnichannelInput } from './components/OmnichannelInput';
import { AgentLiveTrace } from './components/AgentLiveTrace';
import { SplitScreenReview } from './components/SplitScreenReview';
import { ErpExportPanel } from './components/ErpExportPanel';
import { agentClient } from './api/agentClient';
import {
  ResolvedLineItem,
  InventoryCheckResult,
  SystemHealth,
  TraceEvent,
  ProcessInputResponse,
  ApproveAndExportResponse
} from './types/erp';
import { ExportResult } from './services/hotfolderService';

export const App: React.FC = () => {
  // Application State
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [isHealthChecking, setIsHealthChecking] = useState<boolean>(false);

  // Active Processing State
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [taskId, setTaskId] = useState<string>('');
  const [customerId, setCustomerId] = useState<string>('DE-10021');
  const [channel, setChannel] = useState<string>('email');
  const [rawText, setRawText] = useState<string>('');

  // Results State
  const [items, setItems] = useState<ResolvedLineItem[]>([]);
  const [inventoryChecks, setInventoryChecks] = useState<InventoryCheckResult[]>([]);
  const [overallConfidence, setOverallConfidence] = useState<number>(1.0);
  const [totalNet, setTotalNet] = useState<number>(0);
  const [totalGross, setTotalGross] = useState<number>(0);
  const [requiresReview, setRequiresReview] = useState<boolean>(false);
  const [reviewReasons, setReviewReasons] = useState<string[]>([]);

  // SSE Trace Events
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [activeNode, setActiveNode] = useState<string | undefined>(undefined);

  // Health check on mount & periodic polling
  const fetchHealth = async () => {
    setIsHealthChecking(true);
    try {
      const data = await agentClient.getHealth();
      setHealth(data);
    } catch (err) {
      console.warn('Backend offline or health check failed', err);
      setHealth(null);
    } finally {
      setIsHealthChecking(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  // Handle Order Ingestion & LangGraph Processing
  const handleProcessOrder = async (
    formData: FormData,
    selectedCustomerId: string,
    selectedChannel: string,
    inputRawText: string
  ) => {
    setIsProcessing(true);
    setCustomerId(selectedCustomerId);
    setChannel(selectedChannel);
    setRawText(inputRawText);
    setTraceEvents([]);
    setActiveNode('classify_intent');

    // Generate client-side task id for SSE stream
    const clientTaskId = `task-${Date.now()}`;
    setTaskId(clientTaskId);

    // Subscribe to SSE stream for live trace visualization
    const unsubscribe = agentClient.subscribeTrace(
      clientTaskId,
      (event: TraceEvent) => {
        setTraceEvents((prev) => {
          const filtered = prev.filter((e) => e.node !== event.node);
          return [...filtered, event];
        });
        setActiveNode(event.node);
      },
      () => {
        setActiveNode(undefined);
      }
    );

    try {
      const result: ProcessInputResponse = await agentClient.processInput(formData);
      setTaskId(result.task_id);
      setItems(result.resolved_items);
      setInventoryChecks(result.inventory_checks);
      setOverallConfidence(result.overall_confidence);
      setTotalNet(result.total_net_amount);
      setTotalGross(result.total_gross_amount);
      setRequiresReview(result.requires_human_review);
      setReviewReasons(result.review_reasons);

      // Populate final trace steps
      if (result.execution_trace) {
        setTraceEvents(
          result.execution_trace.map((node) => ({
            node,
            status: 'COMPLETED',
          }))
        );
      }
    } catch (err: any) {
      console.error('Processing order failed', err);
      alert(`Verarbeitung fehlgeschlagen: ${err.message || String(err)}`);
    } finally {
      setIsProcessing(false);
      unsubscribe();
    }
  };

  // Handle clerk updating a line item
  const handleUpdateItem = (index: number, updated: ResolvedLineItem) => {
    const newItems = [...items];
    newItems[index] = updated;
    setItems(newItems);

    // Recalculate totals
    const newNet = newItems.reduce((acc, it) => acc + it.total_price_net, 0);
    const newGross = newNet * 1.19; // 19% standard VAT
    setTotalNet(newNet);
    setTotalGross(newGross);
  };

  // Handle export success
  const handleExportSuccess = (
    apiRes: ApproveAndExportResponse,
    exportRes: ExportResult
  ) => {
    console.info('Export successful:', apiRes, exportRes);
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Navbar */}
      <header className="h-14 border-b border-slate-800 bg-slate-900/90 px-5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-600 to-blue-500 flex items-center justify-center shadow-md">
            <Boxes className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-sm tracking-tight text-slate-100">
                BetriebsPilot AI
              </h1>
              <span className="text-[10px] font-mono bg-sky-950/80 text-sky-400 border border-sky-800/50 px-1.5 py-0.2 rounded">
                v1.0 ERP Cockpit
              </span>
              <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-1.5 py-0.2 rounded border border-slate-700 uppercase">
                {channel}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              Autonomer Back-Office Agent für SAP Business One, Sage 100 & proALPHA
            </p>
          </div>
        </div>

        {/* System Health Indicators */}
        <div className="flex items-center gap-4 text-xs">
          {/* PostgreSQL Indicator */}
          <div
            className="flex items-center gap-1.5"
            title={health?.database.connected ? 'PostgreSQL 16 verbunden' : 'PostgreSQL getrennt'}
          >
            <Database className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400 text-[11px]">ERP DB:</span>
            <span
              className={`w-2 h-2 rounded-full ${
                health?.database.connected ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-red-400'
              }`}
            ></span>
          </div>

          {/* Qdrant Indicator */}
          <div
            className="flex items-center gap-1.5"
            title={health?.qdrant.connected ? 'Qdrant Vector Store online' : 'Qdrant offline'}
          >
            <Cpu className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400 text-[11px]">Qdrant RAG:</span>
            <span
              className={`w-2 h-2 rounded-full ${
                health?.qdrant.connected ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-red-400'
              }`}
            ></span>
          </div>

          {/* LLM Engine Indicator */}
          <div
            className="flex items-center gap-1.5"
            title={health?.llm.reachable ? `LLM online (${health.llm.model})` : 'LLM nicht erreichbar'}
          >
            <Terminal className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-400 text-[11px]">
              {health?.llm.provider === 'ollama' ? 'Local Ollama' : 'Cloud LLM'}:
            </span>
            <span
              className={`w-2 h-2 rounded-full ${
                health?.llm.reachable ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-amber-400'
              }`}
            ></span>
          </div>

          <button
            onClick={fetchHealth}
            disabled={isHealthChecking}
            className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800 transition"
            title="Systemdiagnose aktualisieren"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isHealthChecking ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* Main 3-Column Cockpit Workspace */}
      <main className="flex-1 p-4 grid grid-cols-12 gap-4 min-h-0 bg-slate-950">
        {/* Column 1: Omnichannel Inbound Queue (3 Cols) */}
        <div className="col-span-3 h-full min-h-0">
          <OmnichannelInput
            onProcess={handleProcessOrder}
            isProcessing={isProcessing}
          />
        </div>

        {/* Column 2: Live Trace & Split-Screen Review (6 Cols) */}
        <div className="col-span-6 h-full min-h-0 flex flex-col">
          <AgentLiveTrace
            events={traceEvents}
            isProcessing={isProcessing}
            activeNode={activeNode}
          />
          <div className="flex-1 min-h-0">
            <SplitScreenReview
              rawText={rawText}
              items={items}
              inventoryChecks={inventoryChecks}
              overallConfidence={overallConfidence}
              requiresReview={requiresReview}
              reviewReasons={reviewReasons}
              onUpdateItem={handleUpdateItem}
            />
          </div>
        </div>

        {/* Column 3: ERP Export & Local Hotfolder Writer (3 Cols) */}
        <div className="col-span-3 h-full min-h-0">
          <ErpExportPanel
            taskId={taskId}
            customerId={customerId}
            items={items}
            totalNet={totalNet}
            totalGross={totalGross}
            isProcessing={isProcessing}
            onExportSuccess={handleExportSuccess}
          />
        </div>
      </main>
    </div>
  );
};

export default App;
