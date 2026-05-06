/** Local index of customer chat session IDs so users can reopen past threads (API is per-session only). */

export type ChatSessionSummary = {
  id: string;
  updatedAt: string;
  preview: string;
};

const SESSIONS_INDEX_KEY = "groww_customer_chat_sessions_index_v1";
const MAX_ENTRIES = 50;

type MessageLike = {
  role: string;
  content: string;
  created_at: string;
};

export function loadChatSessionIndex(): ChatSessionSummary[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SESSIONS_INDEX_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (row): row is ChatSessionSummary =>
          row &&
          typeof row === "object" &&
          typeof (row as ChatSessionSummary).id === "string" &&
          typeof (row as ChatSessionSummary).updatedAt === "string" &&
          typeof (row as ChatSessionSummary).preview === "string",
      )
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  } catch {
    return [];
  }
}

export function upsertChatSessionFromMessages(sessionId: string, messages: MessageLike[]): void {
  if (typeof window === "undefined" || !sessionId || messages.length === 0) return;
  const firstUser = messages.find((m) => m.role === "user");
  const preview = (firstUser?.content ?? "Conversation").trim().slice(0, 72) || "Conversation";
  const last = messages[messages.length - 1];
  const updatedAt = last?.created_at ?? new Date().toISOString();
  const existing = loadChatSessionIndex().filter((row) => row.id !== sessionId);
  const next: ChatSessionSummary[] = [{ id: sessionId, updatedAt, preview }, ...existing].slice(0, MAX_ENTRIES);
  window.localStorage.setItem(SESSIONS_INDEX_KEY, JSON.stringify(next));
}
