"use client";

import { ChatPanel } from "@/components/customer/ChatPanel";

type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

interface ChatHistoryProps {
  messages: ChatMessage[];
  disabled: boolean;
  onNewChat: () => void;
}

export function ChatHistory({ messages, disabled, onNewChat }: ChatHistoryProps) {
  return (
    <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Chat history</h3>
        <button
          type="button"
          className="rounded-md border border-groww-border bg-groww-ink/20 px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-groww-ink/30 disabled:opacity-50"
          onClick={onNewChat}
          disabled={disabled}
        >
          New chat
        </button>
      </div>
      <ChatPanel messages={messages} />
    </div>
  );
}
