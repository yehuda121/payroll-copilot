import { useEffect, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import {
  aiMonitoringService,
  type ModelComparisonItem,
} from '../../services/aiMonitoring';
import './admin-ai.css';

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export function AiModelsPage() {
  const [items, setItems] = useState<ModelComparisonItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void aiMonitoringService
      .modelComparison(24)
      .then((data) => {
        if (!cancelled) {
          setItems(data.items ?? []);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError('Unable to load model comparison.');
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
      title="AI Models"
      description="Operational comparison of providers and models (request volume, latency, tokens, cost, success)."
    >
      {loading && <p className="admin-ai-muted">Loading comparison…</p>}
      {error && <p className="admin-ai-error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="admin-ai-muted">No AI calls recorded in this process yet.</p>
      )}
      {items.length > 0 && (
        <div className="admin-ai-table-wrap">
          <table className="admin-ai-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model</th>
                <th>Requests</th>
                <th>Avg latency</th>
                <th>Avg tokens</th>
                <th>Est. cost</th>
                <th>Success rate</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={`${row.provider}:${row.model}`}>
                  <td>{row.provider}</td>
                  <td>{row.model}</td>
                  <td>{row.request_count}</td>
                  <td>{row.average_latency_ms.toFixed(0)} ms</td>
                  <td>{row.average_tokens.toFixed(1)}</td>
                  <td>${row.estimated_cost_usd.toFixed(4)}</td>
                  <td>{pct(row.success_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PortalPage>
  );
}
