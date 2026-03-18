"use client";

import { useState } from "react";

const API = "http://localhost:8000";

interface CardDetail {
  label: string;
  value: string;
}

interface Card {
  title: string;
  details: CardDetail[];
  warning: string | null;
  tier: string;
}

interface Props {
  token: string;
  card: Card;
  onDone: (message: string) => void;
}

export default function ConfirmCard({ token, card, onDone }: Props) {
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");
  const isDestructive = card.tier === "DESTRUCTIVE";

  async function submit(action: "confirm" | "cancel") {
    setState("loading");
    try {
      const res = await fetch(`${API}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token, action }),
      });
      const data = await res.json();
      setState("done");

      if (action === "cancel") {
        onDone("Action cancelled.");
      } else if (res.status === 410) {
        onDone("Confirmation expired. Please re-issue the command.");
      } else if (data.type === "error") {
        onDone(data.message || "Something went wrong.");
      } else {
        onDone(data.message || "Done.");
      }
    } catch {
      setState("idle");
    }
  }

  return (
    <div className={`rounded-xl overflow-hidden border text-sm ${
      isDestructive ? "border-red-400/30" : "border-blue-400/20"
    }`}>
      {/* Header */}
      <div className={`px-4 py-3 flex items-center gap-2 ${
        isDestructive ? "bg-red-950/40" : "bg-blue-950/30"
      }`}>
        <span className="text-lg">{isDestructive ? "⚠️" : "✅"}</span>
        <span className={`font-semibold ${isDestructive ? "text-red-300" : "text-blue-200"}`}>
          {card.title}
        </span>
      </div>

      {/* Details */}
      <div className="bg-[#0F1A2E]/60 px-4 py-3 space-y-2">
        {card.details.map((d, i) => (
          <div key={i} className="flex items-start justify-between gap-4">
            <span className="text-gray-400 text-xs w-28 flex-shrink-0">{d.label}</span>
            <span className="text-gray-100 text-xs text-right">{d.value}</span>
          </div>
        ))}

        {card.warning && (
          <div className="mt-2 pt-2 border-t border-red-500/20 text-red-400 text-xs flex items-center gap-1">
            <span>⚠</span> {card.warning}
          </div>
        )}
      </div>

      {/* Buttons */}
      {state !== "done" && (
        <div className={`px-4 py-3 flex gap-2 ${
          isDestructive ? "bg-red-950/20" : "bg-blue-950/20"
        }`}>
          <button
            onClick={() => submit("confirm")}
            disabled={state === "loading"}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-colors disabled:opacity-50 ${
              isDestructive
                ? "bg-red-600 hover:bg-red-700 text-white"
                : "bg-[#0D9488] hover:bg-teal-600 text-white"
            }`}
          >
            {state === "loading" ? "Processing..." : "Confirm"}
          </button>
          <button
            onClick={() => submit("cancel")}
            disabled={state === "loading"}
            className="flex-1 py-2 text-xs font-semibold rounded-lg border border-gray-600 text-gray-300 hover:bg-gray-700/50 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
