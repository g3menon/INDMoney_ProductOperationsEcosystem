"use client";

export type PromptChip = { id: string; label: string; prompt: string };

interface PromptChipsProps {
  chips: PromptChip[];
  disabled: boolean;
  onSend: (prompt: string) => void;
}

export const FALLBACK_PROMPTS: PromptChip[] = [
  {
    id: "fallback-nav",
    label: "Check NAV",
    prompt: "What is the NAV of HDFC Flexi Cap Fund?",
  },
  {
    id: "fallback-compare",
    label: "Compare flexi caps",
    prompt: "Compare HDFC Flexi Cap and Parag Parikh Flexi Cap",
  },
  {
    id: "fallback-expense",
    label: "Expense ratio",
    prompt: "Explain expense ratio in simple words",
  },
  {
    id: "fallback-book",
    label: "Book advisor",
    prompt: "Book an appointment with an advisor",
  },
  {
    id: "fallback-cancel",
    label: "Cancel booking",
    prompt: "Cancel my booking using booking ID",
  },
];

export function PromptChips({ chips, disabled, onSend }: PromptChipsProps) {
  const visibleChips = chips.length > 0 ? chips : FALLBACK_PROMPTS;

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {visibleChips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          className="pill-chip"
          onClick={() => onSend(chip.prompt)}
          disabled={disabled}
          aria-label={`Send prompt: ${chip.label}`}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}
