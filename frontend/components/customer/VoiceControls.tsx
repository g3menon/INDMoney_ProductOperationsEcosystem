"use client";

type VoiceState = "idle" | "recording" | "processing";

export function VoiceControls({
  state,
  disabled,
  onToggle,
}: {
  state: VoiceState;
  disabled: boolean;
  onToggle: () => void;
}) {
  const label =
    state === "recording" ? "Recording" : state === "processing" ? "Processing" : "Voice message";

  return (
    <button
      type="button"
      className={
        state === "recording"
          ? "focus-ring inline-flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700"
          : "focus-ring inline-flex items-center gap-2 rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent"
      }
      onClick={onToggle}
      disabled={disabled || state === "processing"}
      aria-label={label}
    >
      <span
        className={
          state === "recording"
            ? "h-2 w-2 animate-pulse rounded-full bg-groww-danger"
            : state === "processing"
              ? "h-2 w-2 animate-pulse rounded-full bg-groww-warning"
              : "h-2 w-2 rounded-full bg-groww-accent"
        }
        aria-hidden
      />
      {label}
    </button>
  );
}
