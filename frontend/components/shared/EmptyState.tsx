import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-groww-border bg-white/75 p-6 shadow-sm">
      <h3 className="text-base font-semibold text-groww-text">{title}</h3>
      <p className="mt-2 text-sm text-groww-muted">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
