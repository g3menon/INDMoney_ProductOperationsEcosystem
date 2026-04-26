export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="rounded-lg border border-red-500/30 bg-red-950/30 p-4 text-sm text-red-100"
      role="alert"
    >
      <div className="font-semibold">{title}</div>
      <p className="mt-2 text-red-100/90">{message}</p>
      {onRetry ? (
        <button
          type="button"
          className="mt-3 rounded-md bg-white/10 px-3 py-2 text-xs font-medium text-white hover:bg-white/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent"
          onClick={onRetry}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
