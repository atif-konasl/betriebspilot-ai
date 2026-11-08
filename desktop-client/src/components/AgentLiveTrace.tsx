import React from 'react';
import { CheckCircle2, Loader2, Circle } from 'lucide-react';
import { TraceEvent } from '../types/erp';

interface AgentLiveTraceProps {
  events: TraceEvent[];
  isProcessing: boolean;
  activeNode?: string;
}

const ORDERED_STEPS = [
  { id: 'classify_intent', title: 'Intent Router', desc: 'Erkenne Auftrag / Reklamation' },
  { id: 'ingest_and_resolve', title: '3-Tier Cascade RAG', desc: 'Extraktion & SKU-Matching' },
  { id: 'check_inventory_atp', title: 'ATP-Bestandsprüfung', desc: 'Echtzeit-Lagerverfügbarkeit' },
  { id: 'confidence_gate', title: 'Confidence Gate', desc: 'GoBD-Prüfung & Human-in-the-Loop' },
];

export const AgentLiveTrace: React.FC<AgentLiveTraceProps> = ({
  events,
  isProcessing,
  activeNode,
}) => {
  // Map completed nodes from events
  const completedNodes = new Set(
    events.filter((e) => e.status === 'COMPLETED').map((e) => e.node)
  );

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs mb-3 shadow-sm">
      <div className="flex items-center justify-between mb-2 pb-1 border-b border-slate-800">
        <span className="font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            {isProcessing && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                isProcessing ? 'bg-sky-500' : 'bg-slate-500'
              }`}
            ></span>
          </span>
          LangGraph Agent Execution Trace
        </span>
        {isProcessing && (
          <span className="text-sky-400 font-mono text-[11px] flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Verarbeite...
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-2">
        {ORDERED_STEPS.map((step, index) => {
          const isDone = completedNodes.has(step.id);
          const isRunning = isProcessing && (activeNode === step.id || (!isDone && index === completedNodes.size));

          return (
            <div
              key={step.id}
              className={`flex items-start gap-2 p-2 rounded border transition-all ${
                isDone
                  ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                  : isRunning
                  ? 'bg-sky-950/30 border-sky-500/50 text-sky-200 ring-1 ring-sky-500/30'
                  : 'bg-slate-950/40 border-slate-800/60 text-slate-500'
              }`}
            >
              <div className="mt-0.5">
                {isDone ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : isRunning ? (
                  <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-slate-600" />
                )}
              </div>
              <div className="min-w-0">
                <div className="font-medium truncate text-[11px]">{step.title}</div>
                <div className="text-[10px] text-slate-400 truncate">{step.desc}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
