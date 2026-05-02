export function InlineStatus({
  tone,
  label,
}: {
  tone: "neutral" | "success" | "warning" | "danger";
  label: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : tone === "danger"
          ? "border-red-200 bg-red-50 text-red-700"
          : "border-groww-border bg-white text-groww-muted";
  const dotClass =
    tone === "success"
      ? "bg-groww-success"
      : tone === "warning"
        ? "bg-groww-warning"
        : tone === "danger"
          ? "bg-groww-danger"
          : "bg-groww-faint";
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${toneClass}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} aria-hidden />
      <span>{label}</span>
    </span>
  );
}
