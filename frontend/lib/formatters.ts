/** Operational timestamps: default display context is IST (`Docs/Rules.md` D5 / UI13). */

export const DEFAULT_TZ_LABEL = "Asia/Kolkata (IST)";

export function formatShortIso(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(d);
  } catch {
    return "—";
  }
}
