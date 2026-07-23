type AnalyticsErrorStateProps = {
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
};

export function AnalyticsErrorState({
  title,
  message,
  onRetry,
  retryLabel = 'Retry',
}: AnalyticsErrorStateProps) {
  return (
    <div className="analytics-state analytics-state--error" role="alert">
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry ? (
        <p>
          <button type="button" onClick={onRetry}>
            {retryLabel}
          </button>
        </p>
      ) : null}
    </div>
  );
}
