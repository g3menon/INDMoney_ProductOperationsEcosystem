export function InlineStatus({
  tone,
  label,
}: {
  tone: "neutral" | "success" | "warning" | "danger";
  label: string;
}) {
  const toneClass =
    tone === "success"
      ? "text-emerald-200"
      : tone === "warning"
        ? "text-amber-200"
        : tone === "danger"
          ? "text-red-200"
          : "text-slate-300";
  return (
    <span className={`inline-flex items-center gap-2 text-xs ${toneClass}`}>
      <span className="font-medium">Status:</span>
      <span>{label}</span>
    </span>
  );
}
