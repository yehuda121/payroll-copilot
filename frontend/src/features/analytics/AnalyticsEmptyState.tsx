type AnalyticsEmptyStateProps = {
  title: string;
  description?: string;
};

export function AnalyticsEmptyState({ title, description }: AnalyticsEmptyStateProps) {
  return (
    <div className="analytics-state" role="status">
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
