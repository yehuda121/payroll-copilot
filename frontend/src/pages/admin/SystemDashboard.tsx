import { useEffect, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import {
  aiMonitoringService,
  type AIDashboardSummary,
} from '../../services/aiMonitoring';
import './admin-ai.css';

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function BarList({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, value]) => value));
  return (
    <section className="admin-ai-card">
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="admin-ai-muted">No data yet. Usage appears after AI calls.</p>
      ) : (
        <ul className="admin-ai-bars">
          {entries.map(([label, value]) => (
            <li key={label}>
              <div className="admin-ai-bars__label">
                <span>{label}</span>
                <span>{value.toLocaleString()}</span>
              </div>
              <div className="admin-ai-bars__track">
                <div
                  className="admin-ai-bars__fill"
                  style={{ width: `${Math.max(4, (value / max) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SystemDashboardPage() {
  const [summary, setSummary] = useState<AIDashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void aiMonitoringService
      .dashboard(24)
      .then((data) => {
        if (!cancelled) {
          setSummary(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError('Unable to load AI metrics.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PortalPage
      title="System Dashboard"
      description="Developer AI monitoring: tokens, cost, latency, and reliability rates for this API process."
    >
      {loading && <p className="admin-ai-muted">Loading metrics…</p>}
      {error && <p className="admin-ai-error">{error}</p>}
      {summary && (
        <div className="admin-ai">
          <div className="admin-ai-kpis">
            <div className="admin-ai-kpi">
              <span>Total tokens</span>
              <strong>{summary.total_tokens.toLocaleString()}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Estimated cost</span>
              <strong>${summary.estimated_cost_usd.toFixed(4)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Average latency</span>
              <strong>{summary.average_latency_ms.toFixed(0)} ms</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Error rate</span>
              <strong>{pct(summary.error_rate)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Retry rate</span>
              <strong>{pct(summary.retry_rate)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Fallback rate</span>
              <strong>{pct(summary.fallback_rate)}</strong>
            </div>
          </div>

          <div className="admin-ai-grid">
            <BarList title="Tokens by provider" data={summary.tokens_by_provider} />
            <BarList title="Tokens by model" data={summary.tokens_by_model} />
          </div>
          <p className="admin-ai-muted">
            Requests observed: {summary.request_count.toLocaleString()}. Metrics are
            process-local aggregates plus CloudWatch emission when enabled.
          </p>
        </div>
      )}
    </PortalPage>
  );
}
