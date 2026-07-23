import type { AssistantUsage } from '../../types/assistant';

function formatCost(usd: number): string {
  if (!Number.isFinite(usd) || usd <= 0) return '$0';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

export function AssistantUsageFooter({ usage }: { usage?: AssistantUsage | null }) {
  if (!usage) return null;
  const provider = usage.provider || '—';
  const model = usage.model || '—';
  const latency =
    usage.latency_ms > 0 ? `${(usage.latency_ms / 1000).toFixed(2)}s` : '—';

  return (
    <div className="assistant-usage-footer" aria-label="AI usage">
      <span>
        {provider} · {model}
      </span>
      <span>
        {usage.prompt_tokens}→{usage.completion_tokens} tok ({usage.total_tokens})
      </span>
      <span>{formatCost(usage.estimated_cost_usd)}</span>
      <span>{latency}</span>
      {usage.retry_count > 0 ? <span className="assistant-usage-footer__badge">retry</span> : null}
      {usage.fallback_used ? (
        <span className="assistant-usage-footer__badge">fallback</span>
      ) : null}
    </div>
  );
}
