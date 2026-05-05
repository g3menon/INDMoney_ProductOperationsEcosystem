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
      className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 shadow-sm"
      role="alert"
    >
      <div className="font-semibold">{title}</div>
      <p className="mt-2 text-red-700">{message}</p>
      {onRetry ? (
        <button
          type="button"
          className="focus-ring mt-3 rounded-full bg-white px-3 py-2 text-xs font-semibold text-red-700 shadow-sm hover:bg-red-100"
          onClick={onRetry}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
