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
    <div className="rounded-lg border border-dashed border-groww-border bg-groww-panel/40 p-6">
      <h3 className="text-base font-semibold text-slate-100">{title}</h3>
      <p className="mt-2 text-sm text-slate-400">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
