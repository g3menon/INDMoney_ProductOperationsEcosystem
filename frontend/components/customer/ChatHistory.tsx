"use client";

import { ChatPanel, type ChatMessage } from "@/components/customer/ChatPanel";

interface ChatHistoryProps {
  messages: ChatMessage[];
  disabled: boolean;
  isSending: boolean;
  onNewChat: () => void;
}

export function ChatHistory({ messages, disabled, isSending, onNewChat }: ChatHistoryProps) {
  if (messages.length === 0 && !isSending) return null;

  return (
    <section className="soft-card p-4 md:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-groww-text">Conversation</h3>
          <p className="mt-1 text-xs text-groww-muted">Your assistant thread stays available while this chat is active.</p>
        </div>
        <button
          type="button"
          className="focus-ring rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent disabled:opacity-50"
          onClick={onNewChat}
          disabled={disabled}
        >
          New chat
        </button>
      </div>
      <ChatPanel messages={messages} isSending={isSending} />
    </section>
  );
}
