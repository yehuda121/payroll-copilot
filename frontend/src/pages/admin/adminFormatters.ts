import type { RagEvalMetricValue } from '../../services/ragEvaluation';

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

export function formatRagMetric(metric: RagEvalMetricValue | undefined): {
  label: string;
  unavailable: boolean;
  reason?: string | null;
} {
  if (!metric || metric.status !== 'ok' || metric.value == null) {
    return {
      label: 'Unavailable',
      unavailable: true,
      reason: metric?.reason ?? (metric?.status === 'error' ? 'Metric error' : 'Not computed'),
    };
  }
  return {
    label: `${(metric.value * 100).toFixed(1)}%`,
    unavailable: false,
  };
}

export function formatDelta(value: number | null | undefined): string {
  if (value == null) return '—';
  const pct = (value * 100).toFixed(1);
  return value > 0 ? `+${pct}%` : `${pct}%`;
}

export function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (['COMPLETED', 'ACTIVE', 'APPROVED', 'OK', 'HEALTHY'].includes(normalized)) {
    return 'admin-ai-badge admin-ai-badge--ok';
  }
  if (['PENDING_REVIEW', 'RUNNING', 'UNCERTAIN', 'COMPLETED_WITH_ERRORS'].includes(normalized)) {
    return 'admin-ai-badge admin-ai-badge--warn';
  }
  if (['FAILED', 'REJECTED', 'ERROR'].includes(normalized)) {
    return 'admin-ai-badge admin-ai-badge--danger';
  }
  return 'admin-ai-badge admin-ai-badge--muted';
}
