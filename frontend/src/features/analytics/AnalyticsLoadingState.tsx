import { Skeleton } from '../../components/ui/Skeleton';

type AnalyticsLoadingStateProps = {
  label?: string;
  cards?: number;
};

export function AnalyticsLoadingState({
  label = 'Loading analytics',
  cards = 4,
}: AnalyticsLoadingStateProps) {
  return (
    <div className="analytics-dashboard" aria-busy="true" aria-live="polite" aria-label={label}>
      <div className="analytics-dashboard__grid">
        {Array.from({ length: cards }, (_, index) => (
          <Skeleton key={index} height={72} rounded />
        ))}
      </div>
      <Skeleton height={220} rounded />
    </div>
  );
}
