"use client";

type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

interface ChatPanelProps {
  messages: ChatMessage[];
}

export function ChatPanel({ messages }: ChatPanelProps) {
  return (
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
  );
}
