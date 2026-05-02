"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { BookingCard, type BookingSummary } from "@/components/customer/BookingCard";
import { ChatHistory } from "@/components/customer/ChatHistory";
import type { ChatMessage } from "@/components/customer/ChatPanel";
import { FALLBACK_PROMPTS, PromptChips, type PromptChip } from "@/components/customer/PromptChips";
import { VoiceControls } from "@/components/customer/VoiceControls";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { fetchJson, type ApiEnvelope } from "@/lib/api-client";

type ChatMessageResult = {
  session_id: string;
  assistant_message: string;
  citations?: ChatMessage["citations"];
  created_at: string;
};

type BookingDetail = BookingSummary & {
  customer_name: string;
  customer_email: string;
  preferred_date: string;
  preferred_time: string;
  display_timezone: string;
  created_at: string;
};

type BookingForm = {
  customer_name: string;
  customer_email: string;
  issue_summary: string;
  preferred_date: string;
  preferred_time: string;
};

const STORAGE_KEY = "groww_customer_chat_session_id_v1";

function localId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function tomorrowIsoDate() {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000);
  return date.toISOString().slice(0, 10);
}

const INITIAL_BOOKING_FORM: BookingForm = {
  customer_name: "",
  customer_email: "",
  issue_summary: "",
  preferred_date: tomorrowIsoDate(),
  preferred_time: "10:00",
};

export function CustomerTab() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chips, setChips] = useState<PromptChip[]>(FALLBACK_PROMPTS);
  const [promptIssue, setPromptIssue] = useState(false);

  const [input, setInput] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "processing">("idle");
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [bookingForm, setBookingForm] = useState<BookingForm>(INITIAL_BOOKING_FORM);
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [lastBooking, setLastBooking] = useState<BookingDetail | null>(null);

  const loadHistory = useCallback(async (sid: string) => {
    setLoadingHistory(true);
    try {
      const response = await fetchJson<ChatMessage[]>(`/api/v1/chat/history/${sid}`);
      setMessages((response.data ?? []) as ChatMessage[]);
    } catch {
      setMessages([]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing && existing.trim().length > 0) {
      setSessionId(existing);
      void loadHistory(existing);
    }
  }, [loadHistory]);

  const loadPrompts = useCallback(async () => {
    try {
      const response = await fetchJson<PromptChip[]>("/api/v1/chat/prompts");
      const loaded = (response.data ?? []) as PromptChip[];
      setChips(loaded.length > 0 ? loaded : FALLBACK_PROMPTS);
      setPromptIssue(false);
    } catch {
      setChips(FALLBACK_PROMPTS);
      setPromptIssue(true);
    }
  }, []);

  useEffect(() => {
    void loadPrompts();
  }, [loadPrompts]);

  const canSend = useMemo(() => input.trim().length > 0 && !sending, [input, sending]);

  const clearChat = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setInput("");
    setSendError(null);
    setLastBooking(null);
  }, []);

  const sendMessage = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text || sending) return;

      const now = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: localId("user"),
        session_id: sessionId ?? undefined,
        role: "user",
        content: text,
        created_at: now,
      };

      setSending(true);
      setSendError(null);
      setInput("");
      setMessages((current) => [...current, userMessage]);

      try {
        const payload = { message: text, ...(sessionId ? { session_id: sessionId } : {}) };
        const response: ApiEnvelope<ChatMessageResult> = await fetchJson<ChatMessageResult>("/api/v1/chat/message", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        if (!response.data?.session_id) throw new Error("The assistant could not start the conversation.");

        const newSessionId = response.data.session_id;
        setSessionId(newSessionId);
        window.localStorage.setItem(STORAGE_KEY, newSessionId);

        const assistantMessage: ChatMessage = {
          id: localId("assistant"),
          session_id: newSessionId,
          role: "assistant",
          content: response.data.assistant_message,
          citations: response.data.citations ?? [],
          created_at: response.data.created_at,
        };

        setMessages((current) => [...current, assistantMessage]);
      } catch (e) {
        setSendError(e instanceof Error ? e.message : "The assistant could not send that message. Please try again.");
      } finally {
        setSending(false);
      }
    },
    [sending, sessionId],
  );

  const submitBooking = useCallback(async () => {
    setBookingBusy(true);
    setBookingError(null);
    try {
      const response = await fetchJson<BookingDetail>("/api/v1/booking/create", {
        method: "POST",
        body: JSON.stringify({
          ...bookingForm,
          session_id: sessionId,
          idempotency_key: localId("booking"),
        }),
      });
      if (!response.data?.booking_id) throw new Error("We could not create the advisor request.");

      const booking = response.data;
      setLastBooking(booking);
      setShowBookingForm(false);
      setBookingForm(INITIAL_BOOKING_FORM);
      setMessages((current) => [
        ...current,
        {
          id: localId("assistant-booking"),
          session_id: sessionId ?? undefined,
          role: "assistant",
          content: "Your advisor request has been created. An advisor will review the context before sending the confirmation email.",
          created_at: new Date().toISOString(),
          booking,
        },
      ]);
    } catch (e) {
      setBookingError(e instanceof Error ? e.message : "We could not create the advisor request. Please check the details.");
    } finally {
      setBookingBusy(false);
    }
  }, [bookingForm, sessionId]);

  const handleVoiceToggle = useCallback(() => {
    if (voiceState === "idle") {
      setVoiceState("recording");
      return;
    }
    if (voiceState === "recording") {
      setVoiceState("processing");
      window.setTimeout(() => {
        setInput((current) => current || "I want to book an advisor appointment.");
        setVoiceState("idle");
      }, 900);
    }
  }, [voiceState]);

  return (
    <div className="space-y-5">
      <section className="gradient-halo overflow-hidden rounded-[2rem] border border-white/80 px-5 py-10 shadow-soft md:px-8 md:py-14">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-3xl bg-white text-lg font-bold text-groww-accent shadow-card">
            AI
          </div>
          <h2 className="mt-6 text-4xl font-semibold tracking-tight text-groww-text md:text-5xl">
            How can Groww AI help today?
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-groww-muted">
            Ask about mutual funds, fees, advisor bookings, or booking status.
          </p>
          <div className="mt-7">
            <PromptChips chips={chips} disabled={sending} onSend={(prompt) => void sendMessage(prompt)} />
          </div>
          {promptIssue ? (
            <p className="mt-3 text-xs text-groww-faint">Showing recommended prompts while suggestions refresh.</p>
          ) : null}
        </div>
      </section>

      {loadingHistory ? <LoadingState label="Restoring conversation" /> : null}

      <ChatHistory messages={messages} disabled={sending || bookingBusy} isSending={sending} onNewChat={clearChat} />

      <section className="soft-card p-3 md:p-4">
        <label htmlFor="customer-composer" className="sr-only">
          Ask Groww AI
        </label>
        <div className="rounded-2xl border border-groww-border bg-white p-3 shadow-sm">
          <textarea
            id="customer-composer"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about NAV, fees, fund comparisons, or booking an advisor..."
            className="min-h-[88px] w-full resize-none bg-transparent px-2 py-2 text-sm leading-6 text-groww-text placeholder:text-groww-faint focus:outline-none"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (canSend) void sendMessage(input);
              }
            }}
          />
          <div className="flex flex-col gap-3 border-t border-groww-border pt-3 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-wrap gap-2">
              <VoiceControls state={voiceState} disabled={sending} onToggle={handleVoiceToggle} />
              <button
                type="button"
                className="pill-chip"
                onClick={() => {
                  const target = document.querySelector("[aria-label='Dashboard areas']");
                  target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }}
                disabled={sending}
              >
                Browse prompts
              </button>
              <button type="button" className="pill-chip" onClick={() => setShowBookingForm((open) => !open)} disabled={sending}>
                Book advisor
              </button>
            </div>
            <button
              type="button"
              className="focus-ring flex h-11 w-11 items-center justify-center rounded-full bg-groww-accent text-lg font-semibold text-white shadow-card transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => void sendMessage(input)}
              disabled={!canSend}
              aria-label="Send message"
            >
              {sending ? "..." : ">"}
            </button>
          </div>
        </div>

        {sendError ? <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{sendError}</p> : null}

        {showBookingForm ? (
          <div className="mt-4 rounded-2xl border border-groww-border bg-groww-surfaceSoft p-4">
            <div className="flex flex-col gap-1 border-b border-groww-border pb-3">
              <h3 className="text-sm font-semibold text-groww-text">Book an advisor</h3>
              <p className="text-xs text-groww-muted">Share the minimum details needed for an advisor to approve the request.</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <input
                value={bookingForm.customer_name}
                onChange={(event) => setBookingForm((current) => ({ ...current, customer_name: event.target.value }))}
                placeholder="Customer name"
                className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-2 text-sm"
              />
              <input
                value={bookingForm.customer_email}
                onChange={(event) => setBookingForm((current) => ({ ...current, customer_email: event.target.value }))}
                placeholder="Email"
                className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-2 text-sm"
              />
              <input
                type="date"
                value={bookingForm.preferred_date}
                onChange={(event) => setBookingForm((current) => ({ ...current, preferred_date: event.target.value }))}
                className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-2 text-sm"
              />
              <input
                type="time"
                value={bookingForm.preferred_time}
                onChange={(event) => setBookingForm((current) => ({ ...current, preferred_time: event.target.value }))}
                className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-2 text-sm"
              />
              <textarea
                value={bookingForm.issue_summary}
                onChange={(event) => setBookingForm((current) => ({ ...current, issue_summary: event.target.value }))}
                placeholder="What should the advisor help with?"
                className="focus-ring min-h-[88px] rounded-xl border border-groww-border bg-white px-3 py-2 text-sm md:col-span-2"
              />
            </div>
            {bookingError ? <p className="mt-3 text-sm text-red-700">{bookingError}</p> : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="focus-ring rounded-full border border-groww-border bg-white px-4 py-2 text-xs font-semibold text-groww-muted"
                onClick={() => setShowBookingForm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="focus-ring rounded-full bg-groww-accent px-4 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-50"
                onClick={() => void submitBooking()}
                disabled={
                  bookingBusy ||
                  !bookingForm.customer_name ||
                  !bookingForm.customer_email ||
                  !bookingForm.issue_summary ||
                  !bookingForm.preferred_date ||
                  !bookingForm.preferred_time
                }
              >
                {bookingBusy ? "Creating..." : "Create request"}
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {lastBooking ? (
        <div className="mx-auto max-w-2xl">
          <BookingCard booking={lastBooking} />
        </div>
      ) : null}
    </div>
  );
}
