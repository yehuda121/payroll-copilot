import { useCallback, useEffect, useMemo, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import { useToast } from '../../components/ui/Toast';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  LineChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useAnalyticsResource } from '../../hooks/useAnalyticsResource';
import {
  ragEvaluationService,
  type EvaluationCaseResult,
  type EvaluationRun,
  type RagEvalMetricValue,
} from '../../services/ragEvaluation';
import { formatDateTime, formatDelta, formatRagMetric, statusBadgeClass } from './adminFormatters';
import './admin-ai.css';

const METRIC_KEYS = [
  { key: 'faithfulness' as const, label: 'Faithfulness' },
  { key: 'context_precision' as const, label: 'Context Precision' },
  { key: 'context_recall' as const, label: 'Context Recall' },
  { key: 'answer_relevancy' as const, label: 'Answer Relevancy' },
  { key: 'temporal_accuracy' as const, label: 'Temporal Retrieval Accuracy' },
];

function MetricKpi({ label, metric }: { label: string; metric: RagEvalMetricValue | undefined }) {
  const formatted = formatRagMetric(metric);
  return (
    <div className="admin-ai-kpi">
      <span>{label}</span>
      {formatted.unavailable ? (
        <strong className="admin-ai-metric-unavailable" title={formatted.reason ?? undefined}>
          Unavailable
        </strong>
      ) : (
        <strong>{formatted.label}</strong>
      )}
    </div>
  );
}

function RunMetrics({ run }: { run: EvaluationRun }) {
  return (
    <div className="admin-ai-kpis">
      {METRIC_KEYS.map(({ key, label }) => (
        <MetricKpi key={key} label={label} metric={run[key]} />
      ))}
    </div>
  );
}

function trendRowsFromRuns(runs: EvaluationRun[]) {
  return [...runs]
    .filter((run) => run.status === 'COMPLETED')
    .reverse()
    .map((run) => ({
      time: new Date(run.completed_at ?? run.started_at).toLocaleDateString(),
      faithfulness: run.faithfulness.status === 'ok' ? (run.faithfulness.value ?? 0) * 100 : null,
      context_precision:
        run.context_precision.status === 'ok' ? (run.context_precision.value ?? 0) * 100 : null,
      context_recall: run.context_recall.status === 'ok' ? (run.context_recall.value ?? 0) * 100 : null,
      answer_relevancy:
        run.answer_relevancy.status === 'ok' ? (run.answer_relevancy.value ?? 0) * 100 : null,
      temporal_accuracy:
        run.temporal_accuracy.status === 'ok' ? (run.temporal_accuracy.value ?? 0) * 100 : null,
    }));
}

export function RagEvaluationPage() {
  const { showToast } = useToast();
  const summary = useAnalyticsResource(
    useCallback((signal: AbortSignal) => ragEvaluationService.summary(signal), []),
    [],
    'Unable to load RAG evaluation summary.',
  );
  const runs = useAnalyticsResource(
    useCallback((signal: AbortSignal) => ragEvaluationService.listRuns(50, signal), []),
    [],
    'Unable to load evaluation runs.',
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [cases, setCases] = useState<EvaluationCaseResult[]>([]);
  const [casesLoading, setCasesLoading] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [compareRunA, setCompareRunA] = useState('');
  const [compareRunB, setCompareRunB] = useState('');
  const [compareResult, setCompareResult] = useState<Awaited<
    ReturnType<typeof ragEvaluationService.compare>
  > | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const completedRuns = useMemo(
    () => (runs.data ?? []).filter((run) => run.status === 'COMPLETED'),
    [runs.data],
  );
  const trendRows = useMemo(() => trendRowsFromRuns(completedRuns), [completedRuns]);
  const latestRun = summary.data?.latest_run ?? completedRuns[0] ?? null;

  useEffect(() => {
    if (!selectedRunId) {
      setCases([]);
      setSelectedCaseId(null);
      return;
    }
    const controller = new AbortController();
    setCasesLoading(true);
    void ragEvaluationService
      .listCases(selectedRunId, controller.signal)
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setCasesLoading(false));
    return () => controller.abort();
  }, [selectedRunId]);

  const selectedCase = cases.find((item) => item.case_id === selectedCaseId) ?? null;

  const startEvaluation = async () => {
    setRunning(true);
    try {
      const run = await ragEvaluationService.startRun();
      showToast({ message: `Evaluation started (${run.run_id}).`, tone: 'success' });
      runs.reload();
      summary.reload();
      setSelectedRunId(run.run_id);
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : 'Failed to start evaluation.',
        tone: 'error',
      });
    } finally {
      setRunning(false);
    }
  };

  const runCompare = async () => {
    if (!compareRunA || !compareRunB || compareRunA === compareRunB) {
      showToast({ message: 'Select two different runs to compare.', tone: 'warning' });
      return;
    }
    setCompareLoading(true);
    try {
      const result = await ragEvaluationService.compare(compareRunA, compareRunB);
      setCompareResult(result);
    } catch (err) {
      showToast({ message: err instanceof Error ? err.message : 'Compare failed.', tone: 'error' });
      setCompareResult(null);
    } finally {
      setCompareLoading(false);
    }
  };

  const loading = (summary.loading && !summary.data) || (runs.loading && !runs.data);
  const error = summary.error || runs.error;

  return (
    <PortalPage
      title="RAG Evaluation"
      description="Benchmark legal RAG quality with faithfulness, retrieval, and temporal accuracy metrics."
    >
      <div className="admin-ai-toolbar">
        <button type="button" className="btn btn--primary" onClick={() => void startEvaluation()} disabled={running}>
          {running ? 'Starting…' : 'Run evaluation'}
        </button>
        {summary.data ? (
          <p className="admin-ai-muted">
            RAGAS {summary.data.ragas_available ? `v${summary.data.ragas_version ?? '?'}` : 'unavailable'}
            {summary.data.ragas_import_error ? ` — ${summary.data.ragas_import_error}` : ''}
          </p>
        ) : null}
      </div>

      {loading ? <AnalyticsLoadingState cards={5} label="Loading RAG evaluation" /> : null}

      {error ? (
        <AnalyticsErrorState
          title="Unable to load RAG evaluation"
          message={error}
          onRetry={() => {
            summary.reload();
            runs.reload();
          }}
        />
      ) : null}

      {!loading && !error ? (
        <div className="admin-ai">
          {latestRun ? (
            <>
              <section className="admin-ai-card">
                <h2>Latest completed run</h2>
                <p className="admin-ai-muted">
                  {latestRun.run_id} · dataset {latestRun.dataset_version} ·{' '}
                  {formatDateTime(latestRun.completed_at ?? latestRun.started_at)}
                </p>
                <RunMetrics run={latestRun} />
              </section>
            </>
          ) : (
            <AnalyticsEmptyState
              title="No completed evaluation runs"
              description="Run an evaluation to populate KPIs and trends."
            />
          )}

          {trendRows.length > 1 ? (
            <LineChartCard
              title="Metric trends (completed runs)"
              data={trendRows}
              xKey="time"
              yLabel="%"
              series={[
                {
                  dataKey: 'faithfulness',
                  name: 'Faithfulness',
                  color: ANALYTICS_CHART_COLORS.primary,
                },
                {
                  dataKey: 'context_precision',
                  name: 'Context precision',
                  color: ANALYTICS_CHART_COLORS.secondary,
                },
                {
                  dataKey: 'context_recall',
                  name: 'Context recall',
                  color: ANALYTICS_CHART_COLORS.warning,
                },
                {
                  dataKey: 'answer_relevancy',
                  name: 'Answer relevancy',
                  color: ANALYTICS_CHART_COLORS.danger,
                },
                {
                  dataKey: 'temporal_accuracy',
                  name: 'Temporal accuracy',
                  color: ANALYTICS_CHART_COLORS.primary,
                },
              ]}
            />
          ) : null}

          <section className="admin-ai-card">
            <h2>Run history</h2>
            {(runs.data ?? []).length === 0 ? (
              <p className="admin-ai-muted">No runs yet.</p>
            ) : (
              <div className="admin-ai-table-wrap">
                <table className="admin-ai-table">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Status</th>
                      <th>Cases</th>
                      <th>Started</th>
                      <th>Faithfulness</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(runs.data ?? []).map((run) => {
                      const faithfulness = formatRagMetric(run.faithfulness);
                      return (
                        <tr
                          key={run.run_id}
                          className={selectedRunId === run.run_id ? 'is-selected' : ''}
                          onClick={() => setSelectedRunId(run.run_id)}
                        >
                          <td>{run.run_id}</td>
                          <td>
                            <span className={statusBadgeClass(run.status)}>{run.status}</span>
                          </td>
                          <td>
                            {run.completed_cases}/{run.case_count}
                          </td>
                          <td>{formatDateTime(run.started_at)}</td>
                          <td className={faithfulness.unavailable ? 'admin-ai-metric-unavailable' : ''}>
                            {faithfulness.label}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {selectedRunId ? (
            <div className="admin-ai-split">
              <section className="admin-ai-card">
                <h2>Cases — {selectedRunId}</h2>
                {casesLoading ? <p className="admin-ai-muted">Loading cases…</p> : null}
                {!casesLoading && cases.length === 0 ? (
                  <p className="admin-ai-muted">No cases for this run.</p>
                ) : null}
                {cases.length > 0 ? (
                  <div className="admin-ai-table-wrap">
                    <table className="admin-ai-table">
                      <thead>
                        <tr>
                          <th>Case</th>
                          <th>Status</th>
                          <th>Temporal</th>
                          <th>Faithfulness</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cases.map((item) => {
                          const faithfulness = formatRagMetric(item.faithfulness);
                          return (
                            <tr
                              key={item.case_id}
                              className={selectedCaseId === item.case_id ? 'is-selected' : ''}
                              onClick={() => setSelectedCaseId(item.case_id)}
                            >
                              <td>{item.case_id}</td>
                              <td>{item.status}</td>
                              <td>{item.temporal_pass == null ? '—' : item.temporal_pass ? 'Pass' : 'Fail'}</td>
                              <td className={faithfulness.unavailable ? 'admin-ai-metric-unavailable' : ''}>
                                {faithfulness.label}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </section>
              <aside className="admin-ai-detail">
                <h3>Case detail</h3>
                {!selectedCase ? <p className="admin-ai-muted">Select a case.</p> : null}
                {selectedCase ? (
                  <>
                    <dl>
                      <div>
                        <dt>Question</dt>
                        <dd>{selectedCase.question}</dd>
                      </div>
                      <div>
                        <dt>Effective date</dt>
                        <dd>{selectedCase.effective_date ?? '—'}</dd>
                      </div>
                      <div>
                        <dt>Expected rules</dt>
                        <dd>{selectedCase.expected_rule_ids.join(', ') || '—'}</dd>
                      </div>
                      <div>
                        <dt>Retrieved rules</dt>
                        <dd>{selectedCase.retrieved_rule_ids.join(', ') || '—'}</dd>
                      </div>
                      <div>
                        <dt>Retrieval mode</dt>
                        <dd>{selectedCase.retrieval_mode ?? '—'}</dd>
                      </div>
                    </dl>
                    <h3>Generated answer</h3>
                    <pre className="admin-ai-pre">{selectedCase.generated_answer || '—'}</pre>
                    <h3>Reference answer</h3>
                    <pre className="admin-ai-pre">{selectedCase.reference_answer || '—'}</pre>
                    {selectedCase.error ? (
                      <p className="admin-ai-error">{selectedCase.error}</p>
                    ) : null}
                  </>
                ) : null}
              </aside>
            </div>
          ) : null}

          <section className="admin-ai-card">
            <h2>Compare runs</h2>
            <div className="admin-ai-toolbar">
              <label className="admin-ai-window">
                <span>Run A</span>
                <select value={compareRunA} onChange={(event) => setCompareRunA(event.target.value)}>
                  <option value="">Select…</option>
                  {completedRuns.map((run) => (
                    <option key={run.run_id} value={run.run_id}>
                      {run.run_id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="admin-ai-window">
                <span>Run B</span>
                <select value={compareRunB} onChange={(event) => setCompareRunB(event.target.value)}>
                  <option value="">Select…</option>
                  {completedRuns.map((run) => (
                    <option key={run.run_id} value={run.run_id}>
                      {run.run_id}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => void runCompare()}
                disabled={compareLoading}
              >
                {compareLoading ? 'Comparing…' : 'Compare'}
              </button>
            </div>
            {compareResult ? (
              <>
                {compareResult.dataset_version_mismatch ? (
                  <p className="admin-ai-muted">Dataset versions differ — compare with caution.</p>
                ) : null}
                <div className="admin-ai-kpis">
                  {METRIC_KEYS.map(({ key, label }) => (
                    <div className="admin-ai-kpi" key={key}>
                      <span>{label} Δ</span>
                      <strong>{formatDelta(compareResult.deltas[key])}</strong>
                    </div>
                  ))}
                </div>
                <p className="admin-ai-muted">
                  Improved: {compareResult.improved_cases.length} · Regressed:{' '}
                  {compareResult.regressed_cases.length}
                </p>
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </PortalPage>
  );
}
