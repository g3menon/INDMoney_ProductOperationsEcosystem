"use client";

export function VoiceControls({
  active,
  unsupported,
  onToggle,
}: {
  active: boolean;
  unsupported: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={
        active
          ? "focus-ring relative flex h-10 w-10 items-center justify-center rounded-full bg-groww-accent text-white shadow-card before:absolute before:inset-[-6px] before:animate-pulse before:rounded-full before:border before:border-groww-accent/30"
          : "focus-ring flex h-10 w-10 items-center justify-center rounded-full border border-groww-border bg-white text-groww-muted shadow-sm hover:text-groww-accent"
      }
      onClick={onToggle}
      disabled={unsupported}
      aria-label={active ? "Stop listening" : "Start voice input"}
      title={unsupported ? "Voice input is not supported in this browser" : active ? "Stop listening" : "Start voice input"}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M12 14.5a3 3 0 0 0 3-3v-5a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M18.5 11.5a6.5 6.5 0 0 1-13 0M12 18v3M9 21h6"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
