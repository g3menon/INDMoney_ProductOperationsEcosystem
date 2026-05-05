export function LoadingState({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-3 rounded-2xl border border-groww-border bg-white px-4 py-3 text-sm text-groww-muted shadow-sm"
      role="status"
      aria-live="polite"
    >
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-groww-border border-t-groww-accent"
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
