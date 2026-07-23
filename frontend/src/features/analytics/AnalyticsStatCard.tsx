type AnalyticsStatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
};

export function AnalyticsStatCard({ label, value, hint }: AnalyticsStatCardProps) {
  return (
    <article className="analytics-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <span>{hint}</span> : null}
    </article>
  );
}
