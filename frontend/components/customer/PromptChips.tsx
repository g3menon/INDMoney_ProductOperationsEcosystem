"use client";

type PromptChip = { id: string; label: string; prompt: string };

interface PromptChipsProps {
  chips: PromptChip[];
  disabled: boolean;
  onSend: (prompt: string) => void;
}

export function PromptChips({ chips, disabled, onSend }: PromptChipsProps) {
  if (chips.length === 0) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {chips.map((c) => (
        <button
          key={c.id}
          type="button"
          className="rounded-full border border-groww-border bg-groww-ink/30 px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-groww-ink/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
          onClick={() => onSend(c.prompt)}
          disabled={disabled}
          aria-label={`Send prompt chip: ${c.label}`}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
