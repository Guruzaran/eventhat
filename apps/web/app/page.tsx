"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const API = "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function login(email: string, label: string) {
    setLoading(label);
    setError(null);
    try {
      const res = await fetch(`${API}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Login failed");
        return;
      }
      router.push("/chat");
    } catch {
      setError("Could not connect to API. Is the backend running on port 8000?");
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="min-h-screen bg-[#080C14] flex items-center justify-center">
      <div className="w-full max-w-sm space-y-8 px-6">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="text-4xl font-bold text-white tracking-tight">
            event<span className="text-[#0D9488]">hat</span>
          </div>
          <p className="text-sm text-gray-400">
            AI-powered event coordination
          </p>
        </div>

        {/* Buttons */}
        <div className="space-y-3">
          <button
            onClick={() => login("organizer@acme.com", "organizer")}
            disabled={!!loading}
            className="w-full py-3 px-4 bg-[#1A56DB] hover:bg-blue-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading === "organizer" ? (
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            ) : "⚡"}
            Login as Alex (Organizer)
          </button>

          <button
            onClick={() => login("participant@acme.com", "participant")}
            disabled={!!loading}
            className="w-full py-3 px-4 bg-[#0F1F3D] hover:bg-slate-700 disabled:opacity-50 text-white font-medium rounded-lg border border-slate-600 transition-colors flex items-center justify-center gap-2"
          >
            {loading === "participant" ? (
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            ) : "👤"}
            Login as Jamie (Participant)
          </button>
        </div>

        {error && (
          <p className="text-red-400 text-sm text-center">{error}</p>
        )}

        <p className="text-xs text-gray-600 text-center">
          Demo mode — no password required
        </p>
      </div>
    </main>
  );
}
