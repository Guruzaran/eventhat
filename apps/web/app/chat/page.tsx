"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import PipelineSidebar, { usePipelineAnimation } from "@/components/PipelineSidebar";
import MessageBubble from "@/components/MessageBubble";
import ConfirmCard from "@/components/ConfirmCard";

const API = "http://localhost:8000";

const SUGGESTIONS = [
  "Create a volunteer event next month with 3 shifts of 10 people",
  "List all my events",
  "Show context",
  "Publish the event",
  "Show who signed up",
];

interface CardDetail {
  label: string;
  value: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  cli?: string | null;
  type?: string;
  token?: string;
  card?: {
    title: string;
    details: CardDetail[];
    warning: string | null;
    tier: string;
  };
}

interface AuditEntry {
  id: string;
  raw_cli: string;
  result_status: string;
  created_at: string;
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [activeCli, setActiveCli] = useState<string | null>(null);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [user, setUser] = useState<{ display_name: string; role: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { layers, animate } = usePipelineAnimation();

  // Auth check
  useEffect(() => {
    fetch(`${API}/me`, { credentials: "include" })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) { router.push("/"); return; }
        setUser(data.user);
      });
  }, [router]);

  // Load audit log
  useEffect(() => {
    fetchAudit();
  }, []);

  async function fetchAudit() {
    try {
      const res = await fetch(`${API}/audit`, { credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        setAuditLog(data.audit || []);
      }
    } catch { /* ignore */ }
  }

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(text: string) {
    if (!text.trim() || sending) return;
    setInput("");
    setSending(true);

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
    };
    setMessages(prev => [...prev, userMsg]);

    // Animate layers 0 (channel) and 1 (compiler) while waiting
    animate(1);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text }),
      });

      const data = await res.json();
      setActiveCli(data.cli || null);

      if (data.type === "confirmation_required") {
        // Animate through gate (layer 3)
        await animate(3);
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I need your confirmation before proceeding:",
          cli: data.cli,
          type: "confirmation_required",
          token: data.token,
          card: data.card,
        };
        setMessages(prev => [...prev, assistantMsg]);

      } else if (data.type === "success") {
        // Animate full pipeline
        await animate(5);
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.message,
          cli: data.cli,
        };
        setMessages(prev => [...prev, assistantMsg]);
        fetchAudit();

      } else {
        // parse_error or error
        await animate(2, true);
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.message || "Something went wrong.",
          cli: data.cli,
        };
        setMessages(prev => [...prev, assistantMsg]);
      }
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Could not reach the API. Is the backend running?",
      }]);
    } finally {
      setSending(false);
    }
  }

  function handleConfirmDone(msgId: string, result: string) {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, type: "done", content: result } : m
    ));
    fetchAudit();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  // Auto-resize textarea
  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  }

  return (
    <div className="flex h-screen bg-[#F8FAFC] overflow-hidden">
      {/* Sidebar */}
      <PipelineSidebar layers={layers} activeCli={activeCli} auditLog={auditLog} />

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="h-14 border-b border-gray-200 bg-white flex items-center justify-between px-6 flex-shrink-0">
          <div className="text-sm font-medium text-gray-700">
            {user ? (
              <>
                <span className="text-gray-400">Logged in as </span>
                <span>{user.display_name}</span>
                <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                  {user.role}
                </span>
              </>
            ) : "Loading..."}
          </div>
          <button
            onClick={async () => {
              await fetch(`${API}/logout`, { method: "POST", credentials: "include" });
              router.push("/");
            }}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            Logout
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-20 space-y-2">
              <div className="text-3xl">⚡</div>
              <p className="text-sm">Type a message or pick a suggestion below</p>
            </div>
          )}

          {messages.map(msg => (
            <div key={msg.id}>
              <MessageBubble role={msg.role} content={msg.content} />
              {msg.type === "confirmation_required" && msg.token && msg.card && (
                <div className="ml-11 mt-2 max-w-sm">
                  <ConfirmCard
                    token={msg.token}
                    card={msg.card}
                    onDone={(result) => handleConfirmDone(msg.id, result)}
                  />
                </div>
              )}
            </div>
          ))}

          {sending && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-[#0D9488] flex items-center justify-center text-xs text-white">⚡</div>
              <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Suggestion chips */}
        <div className="px-6 pb-2 flex gap-2 overflow-x-auto flex-shrink-0">
          {SUGGESTIONS.map(s => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              disabled={sending}
              className="flex-shrink-0 text-xs px-3 py-1.5 bg-white border border-gray-200 hover:border-blue-300 hover:bg-blue-50 rounded-full text-gray-600 transition-colors disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input bar */}
        <div className="px-6 pb-6 flex-shrink-0">
          <div className="flex gap-3 bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm focus-within:border-blue-400 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              disabled={sending}
              className="flex-1 resize-none outline-none text-sm text-gray-700 placeholder-gray-400 bg-transparent"
              style={{ maxHeight: "120px" }}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || sending}
              className="self-end w-8 h-8 bg-[#1A56DB] hover:bg-blue-700 disabled:opacity-40 rounded-lg flex items-center justify-center transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-1.5 ml-1">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  );
}
