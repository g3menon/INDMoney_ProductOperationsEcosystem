"use client";

type CitationSource = {
  source_url: string;
  doc_type: string;
  title: string;
  last_checked: string;
  relevant_quote?: string | null;
};

type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  citations?: CitationSource[];
};

interface ChatPanelProps {
  messages: ChatMessage[];
}

function CitationCard({ citation }: { citation: CitationSource }) {
  const label =
    citation.doc_type === "fee_explainer"
      ? "Fee Explainer"
      : "Fund Page";

  return (
    <a
      href={citation.source_url}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-2 block rounded border border-groww-border/60 bg-groww-ink/20 px-3 py-2 text-xs transition-colors hover:border-groww-border hover:bg-groww-ink/40"
      aria-label={`Source: ${citation.title}`}
    >
      <div className="flex items-center gap-1.5">
        <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300">
          {label}
        </span>
        <span className="truncate font-medium text-slate-200">{citation.title}</span>
      </div>
      {citation.relevant_quote && (
        <p className="mt-1 line-clamp-2 text-slate-400">"{citation.relevant_quote}"</p>
      )}
      <p className="mt-0.5 text-slate-500">
        Last checked: {citation.last_checked}
      </p>
    </a>
  );
}

export function ChatPanel({ messages }: ChatPanelProps) {
  return (
    <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-2">
      {messages.length === 0 ? (
        <p className="text-sm text-slate-400">Send a message to start the chat.</p>
      ) : (
        messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[80%] rounded-lg bg-white/10 px-3 py-2 text-sm text-white"
                  : "max-w-[80%]"
              }
            >
              {m.role === "user" ? (
                <span>{m.content}</span>
              ) : (
                <>
                  <div className="rounded-lg border border-groww-border/70 bg-groww-ink/30 px-3 py-2 text-sm text-slate-100">
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-1 space-y-1" aria-label="Sources">
                      <p className="px-1 text-[10px] uppercase tracking-wide text-slate-500">
                        Sources
                      </p>
                      {m.citations.map((c) => (
                        <CitationCard key={c.source_url} citation={c} />
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
