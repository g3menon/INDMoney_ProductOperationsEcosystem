"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/shared/ErrorState";
import { InlineStatus } from "@/components/shared/InlineStatus";
import { LoadingState } from "@/components/shared/LoadingState";
import { fetchJson, type ApiEnvelope } from "@/lib/api-client";

type PromptChip = { id: string; label: string; prompt: string };

type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type ChatMessageResult = { session_id: string; assistant_message: string; created_at: string };

const STORAGE_KEY = "groww_customer_chat_session_id_v1";

export function CustomerTab() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chips, setChips] = useState<PromptChip[]>([]);

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState<"none" | "loading" | "sending">("none");
  const [error, setError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing && existing.trim().length > 0) setSessionId(existing);
  }, []);

  const loadPrompts = useCallback(async () => {
    setBusy("loading");
    setError(null);
    try {
      const r = await fetchJson<PromptChip[]>("/api/v1/chat/prompts");
      setChips((r.data ?? []) as PromptChip[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setChips([]);
    } finally {
      setBusy("none");
    }
  }, []);

  const loadHistory = useCallback(
    async (sid: string) => {
      setBusy("loading");
      setError(null);
      try {
        const r = await fetchJson<ChatMessage[]>(`/api/v1/chat/history/${sid}`);
        setMessages((r.data ?? []) as ChatMessage[]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        setMessages([]);
      } finally {
        setBusy("none");
      }
    },
    [],
  );

  useEffect(() => {
    void loadPrompts();
  }, [loadPrompts]);

  useEffect(() => {
    if (!sessionId) return;
    void loadHistory(sessionId);
  }, [sessionId, loadHistory]);

  const canSend = useMemo(() => input.trim().length > 0 && busy !== "sending", [input, busy]);

  const clearChat = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setInput("");
    setSendError(null);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      setBusy("sending");
      setSendError(null);
      try {
        const payload = { message: text, ...(sessionId ? { session_id: sessionId } : {}) };
        const r: ApiEnvelope<ChatMessageResult> = await fetchJson<ChatMessageResult>("/api/v1/chat/message", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        if (!r.data?.session_id) throw new Error("Missing session id in response.");

        const newSid = r.data.session_id;
        setSessionId(newSid);
        window.localStorage.setItem(STORAGE_KEY, newSid);

        await loadHistory(newSid);
        setInput("");
      } catch (e) {
        setSendError(e instanceof Error ? e.message : "Failed to send message");
      } finally {
        setBusy("none");
      }
    },
    [loadHistory, sessionId],
  );

  if (error) return <ErrorState title="Chat API error" message={error} onRetry={() => void loadPrompts()} />;
  if (busy === "loading" && messages.length === 0)
    return <LoadingState label="Loading customer chat…" />;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Customer chat (Phase 3)</h2>
            <p className="mt-1 text-sm text-slate-400">Text chat + prompt chips. History is persisted per session.</p>
          </div>
          <InlineStatus tone={sessionId ? "success" : "warning"} label={sessionId ? `Session: ${sessionId}` : "No active session"} />
        </div>

        {chips.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {chips.map((c) => (
              <button
                key={c.id}
                type="button"
                className="rounded-full border border-groww-border bg-groww-ink/30 px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-groww-ink/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
                onClick={() => void sendMessage(c.prompt)}
                disabled={busy !== "none"}
                aria-label={`Send prompt chip: ${c.label}`}
              >
                {c.label}
              </button>
            ))}
          </div>
        ) : null}

        {sendError ? <p className="mt-3 text-sm text-amber-200">{sendError}</p> : null}
      </div>

      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Chat history</h3>
          <button
            type="button"
            className="rounded-md border border-groww-border bg-groww-ink/20 px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-groww-ink/30 disabled:opacity-50"
            onClick={() => clearChat()}
            disabled={busy !== "none"}
          >
            New chat
          </button>
        </div>

        <div className="mt-4 max-h-96 space-y-3 overflow-y-auto pr-2">
          {messages.length === 0 ? (
            <p className="text-sm text-slate-400">Send a message to start the chat.</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[80%] rounded-lg bg-white/10 px-3 py-2 text-sm text-white"
                      : "max-w-[80%] rounded-lg border border-groww-border/70 bg-groww-ink/30 px-3 py-2 text-sm text-slate-100"
                  }
                >
                  {m.content}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <h3 className="text-sm font-semibold text-white">Send a message</h3>
        <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-center">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about mutual funds or fees…"
            className="w-full flex-1 rounded-md border border-groww-border bg-groww-ink/50 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent"
            aria-label="Chat input"
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSend) void sendMessage(input);
            }}
          />
          <button
            type="button"
            className="rounded-md bg-groww-accent px-4 py-2 text-xs font-semibold text-groww-ink hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
            onClick={() => void sendMessage(input)}
            disabled={!canSend}
          >
            {busy === "sending" ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
