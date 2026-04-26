/** Lightweight confirmation surface (shared per `Docs/Rules.md` UI15). */

export function ConfirmationBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-emerald-500/30 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-100">
      {message}
    </div>
  );
}
