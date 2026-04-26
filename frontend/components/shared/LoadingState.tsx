export function LoadingState({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-groww-border bg-groww-panel px-4 py-3 text-sm text-slate-200"
      role="status"
      aria-live="polite"
    >
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-500 border-t-groww-accent"
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
