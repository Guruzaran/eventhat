"use client";

import { useEffect, useState } from "react";

export type LayerStatus = "idle" | "active" | "done" | "error";

export interface LayerState {
  name: string;
  label: string;
  status: LayerStatus;
}

const INITIAL_LAYERS: LayerState[] = [
  { name: "channel",  label: "Channel",       status: "idle" },
  { name: "compiler", label: "AI Compiler",    status: "idle" },
  { name: "parser",   label: "Parser",         status: "idle" },
  { name: "gate",     label: "Confirm Gate",   status: "idle" },
  { name: "executor", label: "Executor",       status: "idle" },
  { name: "db",       label: "PostgreSQL",     status: "idle" },
];

const STATUS_COLORS: Record<LayerStatus, string> = {
  idle:   "bg-gray-600",
  active: "bg-yellow-400 animate-pulse",
  done:   "bg-[#0D9488]",
  error:  "bg-red-500",
};

const STATUS_TEXT: Record<LayerStatus, string> = {
  idle:   "waiting",
  active: "processing...",
  done:   "done",
  error:  "error",
};

interface AuditEntry {
  id: string;
  raw_cli: string;
  result_status: string;
  created_at: string;
}

interface Props {
  layers: LayerState[];
  activeCli: string | null;
  auditLog: AuditEntry[];
}

export function usePipelineAnimation() {
  const [layers, setLayers] = useState<LayerState[]>(INITIAL_LAYERS);

  function reset() {
    setLayers(INITIAL_LAYERS.map(l => ({ ...l, status: "idle" })));
  }

  async function animate(throughIndex: number, hasError = false) {
    reset();
    for (let i = 0; i <= throughIndex; i++) {
      await new Promise(r => setTimeout(r, 200));
      setLayers(prev => prev.map((l, idx) => ({
        ...l,
        status: idx < i ? "done" : idx === i ? "active" : "idle",
      })));
    }
    await new Promise(r => setTimeout(r, 300));
    setLayers(prev => prev.map((l, idx) => ({
      ...l,
      status: idx <= throughIndex
        ? (idx === throughIndex && hasError ? "error" : "done")
        : "idle",
    })));
    // Reset to idle after 2s
    await new Promise(r => setTimeout(r, 2000));
    reset();
  }

  return { layers, animate, reset };
}

export default function PipelineSidebar({ layers, activeCli, auditLog }: Props) {
  function syntaxHighlight(cli: string) {
    if (!cli) return null;
    const parts = cli.split(" ");
    return parts.map((part, i) => {
      if (i === 0) return <span key={i} className="text-[#60A5FA]">{part} </span>;
      if (i === 1) return <span key={i} className="text-[#34D399]">{part} </span>;
      if (part.startsWith("--")) return <span key={i} className="text-[#C084FC]">{part} </span>;
      return <span key={i} className="text-yellow-300">{part} </span>;
    });
  }

  const statusBadge: Record<string, string> = {
    success:  "bg-teal-900 text-teal-300",
    error:    "bg-red-900 text-red-300",
    replayed: "bg-blue-900 text-blue-300",
    parse_error: "bg-yellow-900 text-yellow-300",
  };

  return (
    <div className="w-72 min-h-screen bg-[#080C14] border-r border-slate-800 flex flex-col p-4 gap-6">
      {/* Logo */}
      <div className="text-xl font-bold text-white">
        event<span className="text-[#0D9488]">hat</span>
      </div>

      {/* Pipeline layers */}
      <div className="space-y-1">
        <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Pipeline</p>
        {layers.map((layer, i) => (
          <div
            key={layer.name}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300 ${
              layer.status === "active"
                ? "border border-yellow-400/40 bg-yellow-400/5"
                : layer.status === "done"
                ? "border border-teal-500/20 bg-teal-500/5"
                : "border border-transparent"
            }`}
          >
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_COLORS[layer.status]}`} />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gray-300">
                <span className="text-gray-600 mr-1">{i + 1}.</span>
                {layer.label}
              </div>
              <div className="text-xs text-gray-600">{STATUS_TEXT[layer.status]}</div>
            </div>
          </div>
        ))}
      </div>

      {/* CLI display */}
      {activeCli && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 uppercase tracking-widest">CLI Command</p>
          <div className="bg-[#0D1117] border border-slate-700 rounded-lg p-3">
            <code className="text-xs font-mono leading-relaxed break-all">
              {syntaxHighlight(activeCli)}
            </code>
          </div>
        </div>
      )}

      {/* Audit log */}
      <div className="flex-1 space-y-1 overflow-hidden">
        <p className="text-xs text-gray-500 uppercase tracking-widest">Recent Audit</p>
        {auditLog.length === 0 ? (
          <p className="text-xs text-gray-600">No activity yet</p>
        ) : (
          <div className="space-y-1 overflow-y-auto max-h-64">
            {auditLog.slice(0, 10).map(entry => (
              <div key={entry.id} className="bg-[#0D1117] rounded p-2 space-y-1">
                <code className="text-xs text-gray-400 break-all line-clamp-1">
                  {entry.raw_cli}
                </code>
                <span className={`text-xs px-1.5 py-0.5 rounded ${statusBadge[entry.result_status] || "bg-gray-800 text-gray-400"}`}>
                  {entry.result_status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
