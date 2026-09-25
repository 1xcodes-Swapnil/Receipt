interface Props {
  message: string;
  onRetry?: () => void;
}

export function ErrorMessage({ message, onRetry }: Props) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm">
      <div className="flex items-start gap-3">
        <span className="text-red-500 mt-0.5 shrink-0">✕</span>
        <div className="flex-1">
          <p className="text-red-800 font-medium">Error</p>
          <p className="text-red-700 mt-1 font-mono text-xs whitespace-pre-wrap">{message}</p>
        </div>
      </div>
      {onRetry && (
        <div className="mt-3">
          <button onClick={onRetry} className="btn-secondary text-xs">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
