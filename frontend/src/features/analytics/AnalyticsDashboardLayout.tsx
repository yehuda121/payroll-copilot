import type { ReactNode } from 'react';
import './analytics.css';

type AnalyticsDashboardLayoutProps = {
  toolbar?: ReactNode;
  children: ReactNode;
};

/** Shared shell for analytics pages — toolbar + content stack. */
export function AnalyticsDashboardLayout({ toolbar, children }: AnalyticsDashboardLayoutProps) {
  return (
    <div className="analytics-dashboard">
      {toolbar ? <div className="analytics-dashboard__toolbar">{toolbar}</div> : null}
      <div className="analytics-dashboard__stack">{children}</div>
    </div>
  );
}

type AnalyticsStatGridProps = {
  children: ReactNode;
};

export function AnalyticsStatGrid({ children }: AnalyticsStatGridProps) {
  return <div className="analytics-dashboard__grid">{children}</div>;
}
