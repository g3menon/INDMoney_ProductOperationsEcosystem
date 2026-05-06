"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BookingCard, type BookingSummary } from "@/components/customer/BookingCard";
import { ChatHistory } from "@/components/customer/ChatHistory";
import type { ChatMessage } from "@/components/customer/ChatPanel";
import { FALLBACK_PROMPTS, PromptChips, type PromptChip } from "@/components/customer/PromptChips";
import { VoiceControls } from "@/components/customer/VoiceControls";
import { LoadingState } from "@/components/shared/LoadingState";
import { fetchJson, type ApiEnvelope } from "@/lib/api-client";
import { BOOKING_REASONS, CURATED_CUSTOMER_PROMPTS, SUPPORTED_FUNDS, type BookingReason } from "@/lib/customer-config";

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

type WeeklyPulse = {
  themes: { theme: string; summary: string; count: number }[];
};

type BookingSlot = {
  date: string;
  time: string;
  label: string;
};

type ContactDetails = {
  name: string;
  email: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
};

const STORAGE_KEY = "groww_customer_chat_session_id_v1";
const BOOKING_ID_PATTERN = /\bBK-\d{8}-[A-Z0-9]{4,}\b/i;

function localId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isoDateAfter(days: number) {
  const date = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
  return date.toISOString().slice(0, 10);
}

function buildSlots(): BookingSlot[] {
  return [
    { date: isoDateAfter(1), time: "10:00", label: "Tomorrow - 10:00 AM IST" },
    { date: isoDateAfter(2), time: "15:30", label: "Day after tomorrow - 3:30 PM IST" },
  ];
}

function promptFromText(text: string, index: number): PromptChip {
  return { id: `prompt-${index}`, label: text.length > 34 ? `${text.slice(0, 31)}...` : text, prompt: text };
}

function derivePulsePrompts(pulse: WeeklyPulse | null): string[] {
  const themeText = (pulse?.themes ?? []).map((theme) => `${theme.theme} ${theme.summary}`.toLowerCase()).join(" ");
  const prompts = [...CURATED_CUSTOMER_PROMPTS];
  if (themeText.includes("withdraw")) prompts.unshift("I need help with withdrawals and timelines");
  if (themeText.includes("sip") || themeText.includes("mandate")) prompts.unshift("I'm facing SIP or mandate issues");
  if (themeText.includes("tax") || themeText.includes("statement")) prompts.unshift("Help me with statements and tax docs");
  if (themeText.includes("kyc")) prompts.unshift("Book an advisor for KYC help");
  return Array.from(new Set(prompts)).slice(0, 9);
}

function getSpeechRecognitionCtor() {
  if (typeof window === "undefined") return null;
  const win = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return win.SpeechRecognition ?? win.webkitSpeechRecognition ?? null;
}

export function CustomerTab() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chips, setChips] = useState<PromptChip[]>(FALLBACK_PROMPTS);
  const [promptIssue, setPromptIssue] = useState(false);

  const [input, setInput] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const [voiceActive, setVoiceActive] = useState(false);
  const [voiceUnsupported, setVoiceUnsupported] = useState(false);
  const [voiceInterim, setVoiceInterim] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const voiceShouldRunRef = useRef(false);

  const [bookingOpen, setBookingOpen] = useState(false);
  const [selectedReason, setSelectedReason] = useState<BookingReason | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<BookingSlot | null>(null);
  const [contact, setContact] = useState<ContactDetails>({ name: "", email: "" });
  const [bookingBusy, setBookingBusy] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [lastBooking, setLastBooking] = useState<BookingDetail | null>(null);

  const availableSlots = useMemo(() => buildSlots(), []);

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
    setVoiceUnsupported(!getSpeechRecognitionCtor());
  }, [loadHistory]);

  const loadPrompts = useCallback(async () => {
    try {
      const [promptResponse, pulseResponse] = await Promise.all([
        fetchJson<PromptChip[]>("/api/v1/chat/prompts").catch(() => null),
        fetchJson<WeeklyPulse | null>("/api/v1/pulse/current").catch(() => null),
      ]);
      const backendPrompts = ((promptResponse?.data ?? []) as PromptChip[]).filter(Boolean);
      const pulsePrompts = derivePulsePrompts(pulseResponse?.data ?? null).map(promptFromText);
      const merged = [...pulsePrompts, ...backendPrompts].slice(0, 10);
      setChips(merged.length > 0 ? merged : FALLBACK_PROMPTS);
      setPromptIssue(!promptResponse && !pulseResponse);
    } catch {
      setChips(FALLBACK_PROMPTS);
      setPromptIssue(true);
    }
  }, []);

  useEffect(() => {
    void loadPrompts();
  }, [loadPrompts]);

  useEffect(() => {
    return () => {
      voiceShouldRunRef.current = false;
      recognitionRef.current?.stop();
    };
  }, []);

  const canSend = useMemo(() => input.trim().length > 0 && !sending, [input, sending]);

  const clearChat = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setInput("");
    setSendError(null);
    setLastBooking(null);
    setBookingOpen(false);
  }, []);

  const appendAssistant = useCallback((content: string, booking?: BookingSummary) => {
    setMessages((current) => [
      ...current,
      {
        id: localId("assistant"),
        session_id: sessionId ?? undefined,
        role: "assistant",
        content,
        created_at: new Date().toISOString(),
        booking,
      },
    ]);
  }, [sessionId]);

  const cancelBookingFromMessage = useCallback(
    async (text: string) => {
      const bookingId = text.match(BOOKING_ID_PATTERN)?.[0];
      if (!bookingId || !text.toLowerCase().includes("cancel")) return false;
      const response = await fetchJson<BookingDetail>("/api/v1/booking/cancel", {
        method: "POST",
        body: JSON.stringify({ booking_id: bookingId, reason: "Customer requested cancellation from chat." }),
      });
      appendAssistant(
        response.data?.status === "cancelled"
          ? `I cancelled booking ${bookingId}.`
          : `I found booking ${bookingId}, but it could not be cancelled from its current status.`,
      );
      return true;
    },
    [appendAssistant],
  );

  const sendMessage = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text || sending) return;

      const userMessage: ChatMessage = {
        id: localId("user"),
        session_id: sessionId ?? undefined,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };

      setSending(true);
      setSendError(null);
      setInput("");
      setVoiceInterim("");
      setMessages((current) => [...current, userMessage]);

      try {
        if (await cancelBookingFromMessage(text)) return;

        if (text.toLowerCase().includes("book") && text.toLowerCase().includes("advisor")) {
          setBookingOpen(true);
          appendAssistant("I can help with that. Choose a reason below, then pick one of two available advisor slots.");
          return;
        }

        const payload = { message: text, ...(sessionId ? { session_id: sessionId } : {}) };
        const response: ApiEnvelope<ChatMessageResult> = await fetchJson<ChatMessageResult>("/api/v1/chat/message", {
          method: "POST",
          body: JSON.stringify(payload),
        });

        const data = response.data;
        if (!data?.session_id) throw new Error("The assistant could not start the conversation.");

        const newSessionId = data.session_id;
        setSessionId(newSessionId);
        window.localStorage.setItem(STORAGE_KEY, newSessionId);

        setMessages((current) => [
          ...current,
          {
            id: localId("assistant"),
            session_id: newSessionId,
            role: "assistant",
            content: data.assistant_message,
            citations: data.citations ?? [],
            created_at: data.created_at,
          },
        ]);
      } catch (e) {
        setSendError(e instanceof Error ? e.message : "The assistant could not send that message. Please try again.");
      } finally {
        setSending(false);
      }
    },
    [appendAssistant, cancelBookingFromMessage, sending, sessionId],
  );

  const toggleVoice = useCallback(() => {
    if (voiceUnsupported) return;
    if (voiceActive) {
      voiceShouldRunRef.current = false;
      recognitionRef.current?.stop();
      setVoiceActive(false);
      setVoiceInterim("");
      return;
    }

    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setVoiceUnsupported(true);
      setVoiceError("Voice input is not supported in this browser.");
      return;
    }

    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-IN";
    recognitionRef.current = recognition;
    voiceShouldRunRef.current = true;
    setVoiceActive(true);
    setVoiceError(null);

    recognition.onresult = (event) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript.trim();
        if (event.results[i].isFinal) finalTranscript += ` ${transcript}`;
        else interimTranscript += ` ${transcript}`;
      }
      if (finalTranscript.trim()) {
        setInput((current) => `${current}${current.trim() ? " " : ""}${finalTranscript.trim()}`);
      }
      setVoiceInterim(interimTranscript.trim());
    };
    recognition.onerror = (event) => {
      if (event.error && !["no-speech", "aborted"].includes(event.error)) {
        setVoiceError("Voice input paused. Check microphone permission and try again.");
      }
    };
    recognition.onend = () => {
      // Web Speech continuous mode has limited browser support; restarting on end is the most reliable approximation.
      if (voiceShouldRunRef.current) {
        window.setTimeout(() => {
          try {
            recognition.start();
          } catch {
            setVoiceError("Voice input paused. Tap the mic to resume.");
            setVoiceActive(false);
            voiceShouldRunRef.current = false;
          }
        }, 250);
      }
    };
    recognition.start();
  }, [voiceActive, voiceUnsupported]);

  const submitGuidedBooking = useCallback(async () => {
    if (!selectedReason || !selectedSlot) return;
    setBookingBusy(true);
    setBookingError(null);
    try {
      const recentContext = messages
        .slice(-6)
        .map((message) => `${message.role}: ${message.content}`)
        .join(" | ");
      const response = await fetchJson<BookingDetail>("/api/v1/booking/create", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          customer_name: contact.name.trim(),
          customer_email: contact.email.trim(),
          preferred_date: selectedSlot.date,
          preferred_time: selectedSlot.time,
          issue_summary: `${selectedReason.label}: ${selectedReason.summary}. Chat summary: ${recentContext || "Customer requested advisor help."}`,
          idempotency_key: localId(`booking-${selectedReason.id}`),
        }),
      });
      if (!response.data?.booking_id) throw new Error("We could not create the advisor request.");

      const booking = { ...response.data, booking_reason: selectedReason.label };
      setLastBooking(booking);
      setBookingOpen(false);
      setSelectedReason(null);
      setSelectedSlot(null);
      setContact({ name: "", email: "" });
      appendAssistant(
        "Your advisor request has been created. The confirmation email remains pending until an advisor approves it.",
        booking,
      );
    } catch (e) {
      setBookingError(e instanceof Error ? e.message : "We could not create the advisor request. Please check the details.");
    } finally {
      setBookingBusy(false);
    }
  }, [appendAssistant, contact.email, contact.name, messages, selectedReason, selectedSlot, sessionId]);

  const startBooking = useCallback((reason?: BookingReason) => {
    setBookingOpen(true);
    setSelectedReason(reason ?? null);
    setSelectedSlot(null);
    setBookingError(null);
    appendAssistant(
      reason
        ? `Great. I will use ${reason.label} as the booking reason. Choose one of the two available slots.`
        : "Let's book an advisor. Choose the reason that best matches your request.",
    );
  }, [appendAssistant]);

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
            Ask about mutual funds (Motilal & HDFC schemes in our source list), fees, advisor bookings, or booking status.
          </p>
          <div className="mt-7">
            <PromptChips chips={chips} disabled={sending} onSend={(prompt) => void sendMessage(prompt)} />
          </div>
          {promptIssue ? <p className="mt-3 text-xs text-groww-faint">Showing recommended prompts while suggestions refresh.</p> : null}
        </div>
      </section>

      <section className="soft-card p-5">
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-semibold text-groww-text">Explore supported mutual funds</h3>
          <p className="text-sm text-groww-muted">
            Six curated Groww MF pages — same schemes as Deliverables/Resources.md. Tap for a quick overview.
          </p>
        </div>
        <div className="mt-4 flex gap-3 overflow-x-auto pb-2">
          {SUPPORTED_FUNDS.map((fund) => (
            <button
              key={fund.name}
              type="button"
              className="focus-ring flex min-w-[230px] items-center gap-3 rounded-2xl border border-groww-border bg-white p-3 text-left shadow-sm transition hover:border-groww-accent/40 hover:bg-groww-accentSoft/40"
              onClick={() => void sendMessage(`Give me a quick overview of ${fund.name}`)}
              disabled={sending}
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-groww-accentSoft text-xs font-bold text-groww-accent">
                {fund.mark}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-groww-text">{fund.name}</span>
                <span className="mt-0.5 block text-xs text-groww-muted">{fund.category}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      {loadingHistory ? <LoadingState label="Restoring conversation" /> : null}

      <ChatHistory messages={messages} disabled={sending || bookingBusy} isSending={sending} onNewChat={clearChat} />

      {bookingOpen ? (
        <section className="soft-card p-5">
          <div className="flex flex-col gap-1 border-b border-groww-border pb-4">
            <h3 className="text-lg font-semibold text-groww-text">Book an advisor</h3>
            <p className="text-sm text-groww-muted">Choose a reason, pick one of two slots, then share contact details.</p>
          </div>

          <div className="mt-5">
            <p className="text-sm font-semibold text-groww-text">1. Select a booking reason</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {BOOKING_REASONS.map((reason) => (
                <button
                  key={reason.id}
                  type="button"
                  className={
                    selectedReason?.id === reason.id
                      ? "focus-ring rounded-2xl border border-groww-accent bg-groww-accentSoft p-4 text-left shadow-sm"
                      : "focus-ring rounded-2xl border border-groww-border bg-white p-4 text-left shadow-sm hover:border-groww-accent/40"
                  }
                  onClick={() => setSelectedReason(reason)}
                >
                  <span className="text-sm font-semibold text-groww-text">{reason.label}</span>
                  <span className="mt-2 block text-xs leading-5 text-groww-muted">{reason.summary}</span>
                </button>
              ))}
            </div>
          </div>

          {selectedReason ? (
            <div className="mt-6">
              <p className="text-sm font-semibold text-groww-text">2. Pick an available slot</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {availableSlots.map((slot) => (
                  <button
                    key={`${slot.date}-${slot.time}`}
                    type="button"
                    className={
                      selectedSlot?.time === slot.time && selectedSlot.date === slot.date
                        ? "focus-ring rounded-2xl border border-groww-accent bg-groww-accentSoft p-4 text-left shadow-sm"
                        : "focus-ring rounded-2xl border border-groww-border bg-white p-4 text-left shadow-sm hover:border-groww-accent/40"
                    }
                    onClick={() => setSelectedSlot(slot)}
                  >
                    <span className="text-sm font-semibold text-groww-text">{slot.label}</span>
                    <span className="mt-2 block text-xs text-groww-muted">30 minute advisor call</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {selectedReason && selectedSlot ? (
            <div className="mt-6">
              <p className="text-sm font-semibold text-groww-text">3. Confirm contact details</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <input
                  value={contact.name}
                  onChange={(event) => setContact((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Customer name"
                  className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-3 text-sm"
                />
                <input
                  value={contact.email}
                  onChange={(event) => setContact((current) => ({ ...current, email: event.target.value }))}
                  placeholder="Email"
                  className="focus-ring rounded-xl border border-groww-border bg-white px-3 py-3 text-sm"
                />
              </div>
              {bookingError ? <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{bookingError}</p> : null}
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  className="focus-ring rounded-full border border-groww-border bg-white px-4 py-2 text-xs font-semibold text-groww-muted"
                  onClick={() => setBookingOpen(false)}
                >
                  Close
                </button>
                <button
                  type="button"
                  className="focus-ring rounded-full bg-groww-accent px-4 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-50"
                  onClick={() => void submitGuidedBooking()}
                  disabled={bookingBusy || !contact.name.trim() || !contact.email.trim()}
                >
                  {bookingBusy ? "Creating..." : "Create booking request"}
                </button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="soft-card p-3 md:p-4">
        <div className="mb-3 flex flex-wrap gap-2">
          {chips.slice(0, 6).map((chip) => (
            <button key={chip.id} type="button" className="pill-chip" onClick={() => void sendMessage(chip.prompt)} disabled={sending}>
              {chip.label}
            </button>
          ))}
        </div>
        <label htmlFor="customer-composer" className="sr-only">
          Ask Groww AI
        </label>
        <div className={voiceActive ? "rounded-2xl border border-groww-accent bg-white p-3 shadow-card" : "rounded-2xl border border-groww-border bg-white p-3 shadow-sm"}>
          <textarea
            id="customer-composer"
            value={voiceInterim ? `${input}${input.trim() ? " " : ""}${voiceInterim}` : input}
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
          <div className="flex items-center justify-between gap-3 border-t border-groww-border pt-3">
            <div className="flex items-center gap-2">
              <VoiceControls active={voiceActive} unsupported={voiceUnsupported} onToggle={toggleVoice} />
              {voiceActive ? <span className="text-xs font-semibold text-groww-accent">Listening continuously</span> : null}
              {voiceUnsupported ? <span className="text-xs text-groww-faint">Voice unavailable</span> : null}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" className="pill-chip" onClick={() => startBooking()} disabled={sending}>
                Book advisor
              </button>
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
        </div>

        {voiceError ? <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">{voiceError}</p> : null}
        {sendError ? <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{sendError}</p> : null}
      </section>

      <section className="soft-card p-5">
        <h3 className="text-sm font-semibold text-groww-text">Advisor booking shortcuts</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {BOOKING_REASONS.map((reason) => (
            <button key={reason.id} type="button" className="pill-chip" onClick={() => startBooking(reason)}>
              {reason.prompt}
            </button>
          ))}
        </div>
      </section>

      {lastBooking ? (
        <div className="mx-auto max-w-2xl">
          <BookingCard booking={lastBooking} />
        </div>
      ) : null}
    </div>
  );
}
